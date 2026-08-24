"""Properties of the Compose files that no running stack checks — tickets E0-02, E0-03.

Almost every acceptance criterion in E0-02 needs Docker: the stack reaching
healthy, `curl localhost:8000/healthz`, `down -v` then `up -d` twice, and the
API container's `id -u`. Those are the CI `docker` job's job, and the ticket's
definition of done says so plainly — "the health gate in CI is the test". E0-03
is the same shape: `up -d` healthy on three services, a `restart beat` that does
not double-schedule, and a worker that goes unhealthy when Redis stops all need
a daemon. None of them are restated here.

What is here is the small set of properties that go green in every dynamic
check and are still wrong. There are four kinds:

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

    E0-10 adds a second credential of this kind and one difference worth reading
    before editing either set of rules. `CARE_DATABASE_URL` opens the only
    connection in the cluster that can execute the audited reveal, and it sat on
    the same shared anchor until pull request #29, so `worker` and `beat` each
    held a route to any student's name. The difference is that this one is not
    forbidden everywhere: `api` serves the §6.2 queue and must keep it, so the
    rule has to assert a value on one service as well as its absence on the
    others — a stack that blanks it everywhere satisfies the forbidding half and
    has no Care queue at all. The parts `.env` builds it from are in the same
    rule, because `env_file:` hands those over too and `DATABASE_URL` supplies
    the address, so blanking the URL alone leaves the credential in the container
    in three pieces and reads as a complete fix in review.

4.  **What a container can reach through the host filesystem.** A bind mount
    changes nothing about whether the stack comes up, so no dynamic gate sees
    one. `- ./:/app/repo:ro` on `worker` — the edit someone makes to get
    `alembic/` or `scripts/` into the job container — hands that container the
    whole of `.env`, superuser pair included, which is the file the
    `environment:` block above it exists to take two variables back out of.
    Blanking two variables is worth nothing when the file they came from is
    mounted, and the same host path can be spelled several ways or hidden
    behind a named volume's `driver_opts`. So this kind is answered by an
    allowlist over normalised sources — `ALLOWED_BIND_MOUNTS` — rather than by
    a list of paths nobody may mount: a spelling nobody anticipated must fail
    closed, and only a closed set does that. E0-19 added it, and the routes it
    closed are recorded there.

E0-03 adds `worker` and `beat`, and they fall into the first three kinds rather
than into one of their own:

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
  - Neither takes privilege the API image does not, which is the E0-03
    security-review item. Nothing dynamic looks at it: a `privileged: true` or a
    `user: root` on the worker makes the stack come up exactly as before, and
    the containers concerned are the ones that will run E0-13's gateway over
    untrusted comment text.

    **This was written as a comparison against `api` and is not one any more.**
    E0-19's security review defeated the relative form in one line: the
    override's `x-development-source` anchor is merged into all three
    application services, so `privileged: true` written there grants all three
    at once and a rule that asks "does `worker` have more than `api`" sees
    nothing. Measured, with the whole suite green: `privileged: true`,
    `pid: host`, `network_mode: host`, `userns_mode: host`, `devices`, and
    `cap_add: SYS_ADMIN`, every one of them invisible to the comparison. The
    rule is absolute now — no service carries a privilege key at all, unless an
    entry in `ALLOWED_PRIVILEGE_GRANTS` says which file, which service and which
    key. The argument the relative form rested on is recorded with the new rule
    rather than deleted, because it is a good argument that turned out to have a
    hole in it, and the next person to want the comparison back should read why
    it went.
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

The Compose files are parsed in `tests/fixtures/repo.py`, unmerged and one at a
time,
which is the whole point of item 1 — `docker compose config` would merge the
override back in and hide it.

**One section is read merged, and the exception is as load-bearing as the rule.**
Reading the files separately is right for every question about a *service*: what
a service publishes, mounts or blanks is per-file configuration, and which file
says it is the difference between every deployment and a laptop. It is wrong for
the top-level `volumes:` section, because Docker merges that before any service
mounts anything — so the override can redefine a volume the base file mounts,
and E0-19's second security review measured that giving `beat` the host root
with the whole suite green. `merged_volume_bodies` does that one merge, every
mount rule reads its result, and the rule to take from it is: *read the
configuration Docker assembles, wherever Docker assembles one.* Today that is
exactly one section. A second one is a change to this paragraph as well as to
the code.

Most tests below read the base file, because that is the one every deployment
runs. The credential rules read both files, and the line between the two groups
is worth stating precisely, because the original reason for leaving the override
alone still holds everywhere else here.

That reason was: judging the override means modelling Compose's merge rules, and
those are not rules to guess at without a daemon. It applies to any *relative*
question — does this override entry overwrite that base entry, does this service
still publish the port the base file gave it — and none of those are asked of
the override.

It does not apply to a question whose answer is the same under every merge. A
value written in either file is a value some container gets, so "nothing may
read this credential" needs no merge model.

**Where the credential rules come from, and why they now close a set rather than
enumerate places to look.** Four reviewer passes each found the same hole one
spelling further out. Pass 2: nothing read the override at all, so one line in a
shared anchor put the superuser password into three containers with every test
green. Pass 3: the credential travelling inside another key's *value*
(`ALEMBIC_DATABASE_URL: postgresql://${DB_SUPERUSER}:...`), and a service
inheriting the whole of `.env` in the override. Pass 4: one hop of indirection
through `.env` itself, and — worse — that the pass-3 fix had *weakened* the
blanking rule, because "blanked in either document" is unsound in one direction.

The verdict was that this was structural rather than bad luck: every guard was
anchored to a hand-picked subtree of a hand-picked pair of files, so each round
added one more place to look and the next spelling was always just outside it.
`labels`, then `extends`, then `include`, then top-level `secrets`. So the
strategy changed, on Todd's ruling, and the shape below is the result:

  - **The document is walked whole**, minus the one exempt service, rather than
    service by service. Top-level sections, anchors, build arguments and labels
    are covered by not being excluded, which is the opposite of covering them by
    being listed.
  - **Variables are resolved transitively through `.env.example`** before the
    comparison, because Compose expands `${...}` inside dotenv values and the
    repository already depends on that for `DATABASE_URL`.
  - **The set of top-level keys is closed**, and `extends` is refused outright.
    Those two are what make the first two sound: `include` pulls in a file
    nothing here parses, a top-level `secrets` entry names a variable without
    interpolating it, and `extends: {service: db}` makes the one exemption
    transitive. Each is now a red that says "extend this module first" rather
    than a spelling that slips past.
  - **The set of *service* keys is closed too**, which is the same move one
    level in, and E0-19's security review is what bought it. The top-level set
    bounds which sections may appear and says nothing about what a service body
    may carry, so `volumes_from: - db` on `worker` passed every rule in this
    module while granting that container every mount `db` has — the whole
    Postgres data directory, measured with the suite green. Enumerating the
    routes would have been the fourth round of the mistake above, so the answer
    is `ALLOWED_SERVICE_KEYS`: what the two files use today, and a red for
    anything else. `volumes_from`, `cgroup`, `uts`, `runtime` and `develop` were
    all measured going past the guards silently, and the point of a closed set
    is that the sixth one nobody has thought of does not.
  - **And the sets close one level further in wherever an allowed key is itself
    a container.** That sentence is the whole history of this module written
    once: the top-level set admitted `volumes:` and said nothing about
    `driver_opts`; the service set admitted `build:` and said nothing about
    `additional_contexts`, which reads a directory outside the project at build
    time, or `build.privileged`, which builds as root on the host; and it
    admitted `ports:` while nothing read the value, so deleting a `127.0.0.1:`
    prefix published Postgres on every interface. `ALLOWED_BUILD_KEYS` and the
    loopback rule close those two. The question to ask of any new entry on any
    of these lists is what it *contains*.
  - **The set of Compose files is closed too**, which is the same move one level
    out. Everything above reads two hand-picked files; Docker reads whichever of
    eight recognised names it finds, preferring `compose.yaml` over
    `docker-compose.yml`. One added file redirects the entire stack away from
    everything this module describes, without a single assertion changing.

The asymmetry between the two files is load-bearing in two rules and stated in
both: a blank in the base file survives into every deployment, and a blank in
the override exists only where the override is read. The mount allowlist turns
on the same thing — `./backend` mounted over the installed wheel is a
development convenience in one file and a defect in the other — and states it
on `ALLOWED_BIND_MOUNTS`.
"""

import posixpath
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

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

# The Care credential, and the two parts `.env` builds it out of. Named rather
# than derived, for the same reason `SUPERUSER_VARIABLES` above is: these three
# are the subject of a rule rather than an incidental group of variables, and a
# fourth spelling should be a deliberate edit here.
#
# **All three together, because the URL alone is not the credential.**
# `env_file: - .env` hands a container `DB_CARE_USER` and `DB_CARE_PASSWORD` as
# well, and `DATABASE_URL` supplies the host, the port and the database name, so
# a process holding the pair can assemble the connection in one line. Blanking
# the URL and stopping there leaves the credential in `worker` and `beat` in
# three parts, and reads as a complete fix in review — `docs/MISTAKES.md`
# entry 13, whose most recent incident is this one.
CARE_CONNECTION_URL = "CARE_DATABASE_URL"
CARE_CREDENTIAL_PARTS = ("DB_CARE_USER", "DB_CARE_PASSWORD")
CARE_VARIABLES = (CARE_CONNECTION_URL, *CARE_CREDENTIAL_PARTS)

# The one application service that may hold the Care connection. `api` serves
# the §6.2 Care queue and `app.services.safety` opens its pool there; `worker`
# and `beat` never serve it, and `worker` is the process that ships student
# comment text to a third-party model provider.
#
# Like `CREDENTIAL_OWNING_SERVICE` above, this cannot be derived. Every route to
# deriving it — "the service that runs uvicorn", "the service with an HTTP
# health check" — names the same thing one step further away and reads as a rule
# when it is a list of one. A second service serving the Care queue is an
# amendment to ADR 0042, and the right way for that to arrive is this constant
# changing in a reviewed diff.
CARE_SERVING_SERVICE = "api"

# Which single service may carry each of the three with a value in it. They
# differ, and the difference is not tidiness: `api` gets the assembled
# connection because it serves the queue, and `db` gets the two parts because it
# is the server `scripts/db-init` creates the role in — the same reason it is
# the one exemption from the superuser rules above. Neither is allowed both.
CARE_VARIABLE_OWNERS = {
    CARE_CONNECTION_URL: CARE_SERVING_SERVICE,
    **{part: CREDENTIAL_OWNING_SERVICE for part in CARE_CREDENTIAL_PARTS},
}

# The top-level sections these two Compose files may declare. Not a style
# preference: the credential rules walk both documents whole, which makes them
# complete over what is written here and blind to a section that moves
# configuration into another file (`include:`) or names a variable without
# interpolating it (`secrets:`, `configs:`). Each of those was a review finding
# in turn, which is why the answer is a closed set rather than three more cases.
#
# These three are exactly what the two files declare — `name`, `services` and
# `volumes` in the base file, `services` in the override, plus the `x-` anchors
# each of them keeps — and a rule that walks values covers all of them. Anything
# else is a deliberate edit to this module, made in the same change.
#
# `networks` was on this list until a reviewer pointed out that nothing declares
# one. A closed set that admits a feature the repository does not use is not
# closed; it is a smaller open one, with an entry nobody has had to think about.
# When a Compose file first needs a network, the entry comes back in the change
# that adds it, and whoever adds it says here why the rules above still hold
# over it — which is the cost this list exists to impose.
ALLOWED_TOP_LEVEL_KEYS = ("name", "services", "volumes")

# The keys a *service body* may declare — the same closed set one level in, and
# E0-19's security review is what bought it.
#
# The list above bounds which sections may appear and says nothing about what an
# allowed section may carry, so every rule in this module that reads a service
# reads the parts of it somebody thought of. `volumes_from: - db` on `worker` is
# the measurement: it grants that container every mount `db` has, which is the
# entire Postgres data directory, and it passed the whole suite green — the
# mount rules read `volumes:` and there is nothing named there to read.
# `cgroup`, `uts`, `runtime` and `develop` were measured going past just as
# quietly. Adding four denials would have been the fourth round of the mistake
# recorded in this module's docstring, so the answer is the strategy that
# already works here: enumerate what the two files use, refuse the rest.
#
# **Enumerated from the two files as the parser sees them**, which is after
# PyYAML has resolved the `<<:` merges — `api` carries `build`, `env_file` and
# `environment` from `x-application` and they are service keys by the time any
# rule here looks. A list written from the visible lines of the file would be
# three keys short and would fail the base file on its own anchor.
#
# `ports` is on this list because the override declares it; the base file must
# not, and that is a different rule with its own test rather than an absence
# here. No service uses an `x-` extension field, so none is admitted — unlike
# the top level, where the anchors live.
ALLOWED_SERVICE_KEYS = (
    "build",
    "command",
    "depends_on",
    "env_file",
    "environment",
    "expose",
    "healthcheck",
    "image",
    "ports",
    "volumes",
)

# The sub-keys a `build:` section may declare — the closed set one level further
# in, and the second security review is what bought this one too.
#
# Admitting `build` admitted everything under it. Two measurements, both green
# against the whole suite and both confirmed by reading a host file out of the
# built image:
#
#   - `additional_contexts` names a second build context, which a
#     `COPY --from=<name>` in the Dockerfile then reads. The context can be any
#     directory on the host — or a git URL — and `.dockerignore` does not apply
#     to it, so it is a route around every rule this module has about what a
#     container may reach, taken at build time rather than at run time.
#   - `privileged: true` under `build` runs the build itself with full host
#     privileges. It is a different key from the service-level `privileged:` that
#     `PRIVILEGE_KEYS` refuses, and it was outside every rule here.
#
# Enumerated from the two files, which use exactly these two on all five
# services that build: `context: .` and a `dockerfile:` per image. **`args` is
# deliberately not on this list.** Nothing declares one; admitting it because a
# build "usually" has arguments is how `networks` got onto
# `ALLOWED_TOP_LEVEL_KEYS`, and a build argument is also a place a credential
# travels (`test_nothing_outside_the_database_service_reads_the_superuser_credential`
# walks it for exactly that reason). It comes back in the change that first needs
# one.
ALLOWED_BUILD_KEYS = ("context", "dockerfile")

# The host addresses a published port may bind. Two, both loopback: a port bound
# here is reachable from the machine running the stack and from nothing else.
#
# The measurement is the omission rather than a wrong value: dropping the
# `127.0.0.1:` prefix from `db`'s entry in the override publishes Postgres on
# every interface — a laptop on a conference network serving its database to the
# room, which is the sentence the override's own header comment already makes —
# and the whole suite stayed green, because `ports` was an allowed service key
# whose *value* no rule read.
LOOPBACK_HOST_IPS = ("127.0.0.1", "::1")

# Compose gives `x-…` no meaning of its own, so an extension field is inert
# until something merges it — and it is walked like every other value, so its
# contents are not exempt from anything. The anchors live here.
EXTENSION_FIELD_PREFIX = "x-"

# Every file name Docker Compose will pick up at the root of a project: the four
# base names, then the four override names. The source is compose-go's
# `DefaultFileNames` and `DefaultOverrideFileNames`, which is the list
# `docker compose` consults before it has read anything.
#
# **This tuple is a claim about Docker's behaviour, not about this repository**,
# and it is the only thing here that can go stale without anyone touching the
# repository: if a future Compose release recognises a ninth name, this list is
# wrong and nothing local will say so. The symptom would be a file the stack
# reads and this suite does not — which is exactly the failure the rule using it
# exists to prevent, so re-check it against the Compose release notes rather
# than against the tests.
#
# The order below is compose-go's, and only *membership* is load-bearing: the
# rule compares sets. Precedence is why a stray file is dangerous rather than
# merely untidy — `compose.yaml` is preferred over `docker-compose.yml`, which
# was measured against the daemon — but nothing here depends on getting the
# order of any pair right.
COMPOSE_FILE_NAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.override.yml",
    "compose.override.yaml",
    "docker-compose.override.yml",
    "docker-compose.override.yaml",
)

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

# Which service, in which file, may declare which of those keys — and why.
#
# **Empty, and that is the rule rather than a starting point.** No service in
# either Compose file declares any of the keys above: the API image fixes a
# non-root user, and nothing in this stack needs a capability, a namespace or a
# device from the host.
#
# The structure exists because the alternative to an exception structure is an
# exception, and an exception written into a rule is one nobody has to justify.
# An entry here names the file, the service and the key, carries the reason as
# its value, and is checked by a test that refuses one for a key the named
# service does not actually declare — so a permission cannot outlive the grant
# it was written for. It is the same shape as `ALLOWED_BIND_MOUNTS`, for the
# same reason and with the same cost.
ALLOWED_PRIVILEGE_GRANTS: dict[tuple[str, str, str], str] = {}

# Host paths whose contents are, in practice, the host. **This list is the
# test's choice**, not the ticket's: the ticket says "no extra privilege beyond
# the API image", and a bind mount is the everyday way one arrives. The docker
# socket is root on the host; /proc and /sys are the kernel; /etc holds the
# shadow file. A service that mounts one of these has the host, whatever its
# `user:` says.
#
# This comment used to end "…while `api` does not", because the rule that read
# it was a comparison. It is not one now: E0-19's security review defeated the
# relative form through the shared anchor, and the mount rules are absolute over
# both files. Mounting the socket into `api` too is not a way to pass.
SENSITIVE_BIND_SOURCES = frozenset(
    {"/", "/dev", "/etc", "/proc", "/run/docker.sock", "/sys", "/var/run/docker.sock"}
)

# Every host path a service may bind-mount, keyed by the file that declares the
# mount and the service it is declared on. E0-19.
#
# **Why an allowlist and not a longer denylist.** The list above names paths
# whose contents are the host, and it was the whole rule until E0-19. It says
# nothing about `- ./:/app/repo:ro`, which is the mount someone adds to get
# `alembic/` or `scripts/` into the job container: `.env` sits beside
# `docker-compose.yml` in every deployment, because `env_file: - .env` requires
# it, so that one line hands the container the superuser pair the
# `environment:` block two hundred lines above took back out. Any denylist is a
# list of the spellings somebody thought of, and the four reviewer passes
# recorded at the top of this module are what that costs. This is the same move
# as `ALLOWED_TOP_LEVEL_KEYS` and `COMPOSE_FILE_NAMES`: close the set, and a
# mount nobody anticipated fails rather than passes.
#
# **Keyed by file, because the two files are not symmetric**, and it is the same
# asymmetry the blanking rule turns on. `docker-compose.override.yml` is merged
# on a laptop and in CI and is read by no other deployment, so `./backend`
# mounted read-only over the installed wheel is a development convenience there
# (ADR 0011) and would be a defect in `docker-compose.yml`, where every
# deployment reads it. A rule phrased over sources alone would have to permit
# that mount in both files; keyed this way, moving it into the base file is a
# failure that names the file it moved to.
#
# **Sources are written the way a Compose file spells them** and go through
# `normalised_bind_source` against the project directory before any comparison,
# exactly as a source read out of a file does — one helper on both sides, so the
# allowlist cannot be compared against a form it is not written in.
#
# **Enumerated, never speculative.** These four entries are what the two files
# declare today and nothing else: `db` needs `scripts/db-init` mounted at
# `/docker-entrypoint-initdb.d` to create the application and Care roles at
# `initdb` (ADR 0009), and the override's three application services mount the
# checkout in place of the copy the image installed. A fifth entry is a
# deliberate edit here, reviewed as one, and `ALLOWED_BIND_MOUNTS` holding an
# entry no file uses is itself a failure — a permission nobody exercises is one
# nobody re-reads.
ALLOWED_BIND_MOUNTS: dict[tuple[str, str], frozenset[str]] = {
    ("docker-compose.yml", "db"): frozenset({"./scripts/db-init"}),
    ("docker-compose.override.yml", "api"): frozenset({"./backend"}),
    ("docker-compose.override.yml", "worker"): frozenset({"./backend"}),
    ("docker-compose.override.yml", "beat"): frozenset({"./backend"}),
}

# What a top-level `volumes:` entry may say, so that a named volume can be
# resolved to the host path it actually mounts. E0-19's second route: the docker
# socket declared as `- /var/run/docker.sock:/var/run/docker.sock` is caught by
# the rules below, and the identical mount declared as
#
#     volumes:
#       host-root:
#         driver_opts: {type: none, device: /, o: bind}
#
# is the same mount under a name — the service entry names a volume rather than
# a path, so nothing that reads service entries alone can see it. Any `device:`
# works, the project directory included, which makes this a second spelling of
# the allowlist route rather than a separate hazard.
#
# Anything outside this set is **refused rather than ignored**, which is the
# strategy the rest of the module already uses. `external: true` says the volume
# is created somewhere this file cannot see; an `nfs` device is a path on
# another host. Neither is modelled, because neither is used here, and a shape
# this module cannot classify has to fail loudly instead of resolving to "not a
# bind" — that is exactly how a mount slips past a closed set.
#
# `name` and `driver` were on this list until E0-19's security review, admitted
# as inert metadata and read as neither a bind nor a refusal. Both are the
# `external: true` argument word for word. A `name:` attaches the volume to a
# **pre-created** Docker volume under exactly that name, with no project prefix
# applied, and `docker volume create --opt device=/ --opt o=bind --opt type=none`
# is one command: the volume this file describes as ordinary is then the host
# root, and nothing in the file says so. A `driver:` hands the mount to a plugin
# that decides what it is. Both are now refused where `external:` is refused,
# for the reason all three share — the thing being mounted is defined somewhere
# this file cannot see.
READABLE_VOLUME_KEYS = ("driver_opts", "labels")

# The three keys that say "defined elsewhere", refused with their own message,
# because "this module has not been taught to read it" is the wrong sentence for
# them: it is not that the shape is unfamiliar, it is that the answer is not in
# this file at all and no amount of teaching puts it there.
VOLUME_KEYS_NAMING_SOMETHING_ELSE = ("external", "name", "driver")

# What makes a `driver_opts` a bind. `type: none` with a `device:` is the local
# driver's spelling for "mount this host path"; the flags in `o:` are the mount
# options, and `bind` there says the same thing. Either one qualifies, because
# both are written in the wild and Docker accepts both.
BIND_DEVICE_TYPES = ("none",)
BIND_DEVICE_FLAG = "bind"

# The long-form `type:` values a service-level volume entry may carry. `bind`
# names a host path; `volume` names an entry in the top-level section; `tmpfs`
# is memory and touches no host path at all. Anything else — `npipe`, `cluster`,
# `image` — is refused for the same reason an unreadable `driver_opts` is.
BIND_MOUNT_TYPE = "bind"
VOLUME_MOUNT_TYPE = "volume"
HOSTLESS_MOUNT_TYPES = ("tmpfs",)

# What a short-form source has to start with to be a host path rather than a
# volume name, which is Compose's own rule.
HOST_PATH_PREFIXES = ("/", ".", "~")

# Every currency a host bind can be declared in, one per line, so that disabling
# one is a single edit that still parses. `docs/MISTAKES.md` entry 35: a guard
# that enumerates mechanisms has to be required to *find* each one on a subject
# that certainly has it, or a green run cannot tell "nothing mounts the socket"
# from "nothing mounts the socket the one way I looked". The samples proving
# each of these is found live in `BIND_CURRENCY_SAMPLES`, and this tuple is
# deliberately not derived from that table — a control that iterates the thing
# under test cannot notice a deletion.
BIND_DECLARATION_CURRENCIES = (
    "short form, relative source",
    "short form, absolute source",
    "long form, type bind",
    "long form, no type",
    "named volume, driver_opts type none",
    "named volume, driver_opts o flags",
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


def supplies_a_value(declared: str | None) -> bool:
    """Whether an `environment:` entry hands a container something to connect with.

    Three states, and only one of them withholds. An empty value removes what
    `env_file:` already set. A value — a literal, or `${CARE_DATABASE_URL}` —
    supplies one. A *bare* name with no value is the one that reads as harmless
    and is not: `- CARE_DATABASE_URL` in a list, or `CARE_DATABASE_URL:` in a
    mapping, tells Compose to pass the variable through from the host
    environment, which is where the real credential lives. `service_environment`
    above keeps that third case as `None` for exactly this reason.

    Whitespace-only counts as empty, and that is agreement rather than leniency:
    `app.config.Settings` reads a blank `CARE_DATABASE_URL` as absent and strips
    before deciding, so a blanking line that has picked up a space on its way
    through a formatter is still a withheld credential at both layers. The
    superuser rules above compare against `""` exactly, which is a stricter
    reading of a line those services also write by hand; the two are not in
    conflict, and this one is stated where the `Settings` validator can be cited
    for it.
    """
    return declared is None or bool(declared.strip())


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

    **Both files, keyed by service name, and asymmetrically.** Reviewer pass 3
    found that this rule read the base file only, while its own docstring
    claimed it reached every service with nothing carved out by name — a
    `pgweb` service added to the override with `env_file: - .env` and no
    `environment:` block passed the whole suite while holding the credential.

    Pass 4 then found that the fix for that was a *regression*, and the reason is
    worth keeping in front of anyone who edits this rule. The fix said a service
    must be blanked *somewhere*. The two files are not symmetric, so that is
    sound in one direction only: a blank in the base file is in every deployment,
    while a blank in the override is absent from the stack the base file runs
    alone — which is every real deployment and CI's own base-file-only pass.
    Moving the two blanking lines out of the base anchor and into the override —
    the natural "tidy the anchor" edit — put the real password into `api`,
    `worker` and `beat` under `docker compose -f docker-compose.yml config`, with
    73 tests passing and with the *previous* version of this rule catching it.

    So the rule is asymmetric, and each half says what it is protecting:

      - `env_file` declared **in the base file** must be blanked **in the base
        file**, because that is the configuration a deployment reads.
      - `env_file` declared **only in the override** may be blanked in either,
        because the base-alone stack inherits nothing there to blank.

    The other direction — an override that *re-supplies* what the base blanked —
    is not this rule's to catch and is covered absolutely by the tests below,
    which forbid the value outright in either file.

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
        in_base = [body for path, body in bodies if path == base_compose_path]
        blanked_in_base = {
            variable: any(service_environment(body).get(variable) == "" for body in in_base)
            for variable in SUPERUSER_VARIABLES
        }
        blanked_anywhere = {
            variable: any(service_environment(body).get(variable) == "" for _, body in bodies)
            for variable in SUPERUSER_VARIABLES
        }

        if any(declares_env_file(body) for body in in_base):
            for variable in SUPERUSER_VARIABLES:
                if blanked_in_base[variable]:
                    continue
                note = ""
                if blanked_anywhere[variable]:
                    note = (
                        " — the override blanks it, which does not help: the base file is what "
                        "every deployment runs, and what CI's base-file-only pass runs alone"
                    )
                problems.append(
                    f"`{name}` inherits the whole of .env in {base_compose_path.name}, which "
                    f"does not blank {variable}{note}"
                )
        else:
            for variable in SUPERUSER_VARIABLES:
                if not blanked_anywhere[variable]:
                    problems.append(
                        f"`{name}` inherits the whole of .env in "
                        f"{override_compose_path.name} and neither file blanks {variable}"
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


def document_without(document: dict[str, Any], service_name: str) -> dict[str, Any]:
    """The parsed document with one service's subtree taken out.

    So the rule below can be "nothing in this file reads the credential" with a
    single exception carved out structurally, instead of a loop that has to
    remember to look everywhere a value can sit. Everything else in the document
    — other services, top-level sections, the anchors — stays in.
    """
    remainder = {key: value for key, value in document.items() if key != "services"}
    remainder["services"] = {
        name: body for name, body in services_of(document).items() if name != service_name
    }
    return remainder


def transitively_read(
    node: Any,
    walker: Callable[[Any], set[str]],
    values: dict[str, str],
) -> set[str]:
    """Every variable `node` reads, following `.env.example` values one hop at a time.

    Compose's dotenv loader expands `${...}` inside the values in `.env`, and
    this repository already depends on that: `DATABASE_URL` is assembled from
    `DB_APP_USER` and `DB_APP_PASSWORD` that way. So a Compose file that names
    `${SUPERUSER_DATABASE_URL}` reads whatever *that* entry is built from, and a
    rule comparing only the name spelled in the Compose file is looking one
    level above where the credential is.

    Reviewer pass 4 found exactly that, spelled the way someone spells it after
    being told not to put `${DB_SUPERUSER}` in the Compose file directly — which
    makes the next reader of the previous fix its most likely author.

    One hop is followed at a time to a fixpoint, so a chain of any length is
    covered and a cycle terminates.

    **`.env.example` is the map, and the map has to be complete for this to be
    sound.** It is documentation, not the deployed file, so a name it does not
    carry resolves to nothing here and reads as clean — while the operator's
    real `.env` sets it to whatever it likes. What closes that is
    `test_env_example_sync.py::test_every_variable_the_compose_files_interpolate_is_documented`,
    which refuses an interpolation of an undocumented name.

    That test exists because this sentence used to assert it and it was not
    true. The claim was written here as the premise this walk rests on, three
    tickets after the direction it names had quietly not been implemented, and
    the suite stayed green through the exact indirection it was supposed to
    stop. Citing a test as a guarantee is citing a mechanism; run it against the
    case you say it catches before you write the sentence — `docs/MISTAKES.md`
    entry 9. The interlock is real now. It was prose then.
    """
    found = set(walker(node))
    queue = list(found)
    while queue:
        name = queue.pop()
        for other in walker(values.get(name, "")) - found:
            found.add(other)
            queue.append(other)
    return found


def test_nothing_outside_the_database_service_reads_the_superuser_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
    documented_env: dict[str, str],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The credential does not reach a container under some other name, or via `.env`.

    The rule above asks whether `DB_SUPERUSER` is an environment *key*. That is
    one of the ways the value travels and not the only one, and two reviewer
    passes found the others by writing the line E0-04 is actually going to want:

        ALEMBIC_DATABASE_URL: postgresql://${DB_SUPERUSER}:${DB_SUPERUSER_PASSWORD}@db:5432/${DB_NAME}

    and then, once that was caught, the same thing one hop further out — a
    Compose file naming `${SUPERUSER_DATABASE_URL}` and `.env.example` building
    that entry out of the pair. Both put the real password in three containers
    with the suite green. ADR 0009's bound is about the credential reaching an
    application container; it is not about the spelling of the variable it
    arrives in, or about how many hops it took.

    So this rule is shaped to have no edge to step past:

      - it reads *values* rather than keys;
      - it walks the **whole document** with one service removed, rather than a
        list of the places a value can hide. `environment:`, `command:`,
        `build.args`, `labels:`, a top-level `secrets:` block, an anchor nothing
        has merged yet — all covered by not being excluded. An enumeration would
        be a list to keep in step with Compose's schema, and a list nobody
        re-reads is what `docs/MISTAKES.md` entry 1 is mostly made of;
      - it resolves names through `.env.example` transitively first.

    Two other tests hold the edges this one cannot see on its own, and they are
    the reason it is sound rather than merely wide: `include` and top-level
    `secrets` are refused by the closed-set rule below, and `extends` is refused
    outright — otherwise `extends: {service: db}` would inherit the exemption,
    and its cross-file form would put the payload in a document nothing here
    opens.

    The walker is `interpolated_variables`, the same one that decides which
    variables `.env.example` must document, so the two cannot disagree about
    what counts as reading a variable. It works off the parsed document, so a
    commented-out interpolation stops counting the moment it stops being one —
    right rather than a gap, because a `#` line in a YAML file is not
    configuration. (That is the exact opposite of a `#` line inside a workflow's
    `run:` block, where the text is a comment and the step still ships. The two
    are at different layers; `test_ci_health_gate.py` says so at length.)

    `db` is exempt, by name, and it is the only exemption in this module — see
    `CREDENTIAL_OWNING_SERVICE` for why it cannot be derived. The exemption is
    the service body and nothing else: an anchor at the top level that holds the
    credential is flagged even if only `db` merges it, because the top level is
    one `<<:` away from every service. Put it in `services.db` directly.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse holds no "
            "interpolations, and a search that finds none reports every file clean."
        )
    assert documented_env, (
        ".env.example is missing or parsed to nothing, so the transitive step below resolves "
        "no names at all and this rule silently degrades to the one that reviewer pass 4 "
        "broke — the one that sees `${SUPERUSER_DATABASE_URL}` and asks no further."
    )

    values = {name.upper(): value for name, value in documented_env.items()}
    bounded = set(SUPERUSER_VARIABLES)

    def reads(node: Any) -> set[str]:
        return transitively_read(node, interpolated_variables_in, values)

    owner = services_of(base_compose).get(CREDENTIAL_OWNING_SERVICE) or {}
    assert bounded & reads(owner), (
        f"The `{CREDENTIAL_OWNING_SERVICE}` service reads neither of "
        f"{list(SUPERUSER_VARIABLES)}, which is the one service that has to. Either the "
        "walker is looking at the wrong thing or it is finding nothing at all, and a rule "
        "that finds nothing calls every file clean. If the database has genuinely stopped "
        "taking its credentials this way — a secrets file, say — this test needs rewriting "
        "around whatever replaced it, not deleting."
    )

    problems: list[str] = []
    for path, document in documents:
        reached = sorted(bounded & reads(document_without(document, CREDENTIAL_OWNING_SERVICE)))
        if not reached:
            continue
        # Attribution for the message only. The assertion is about the document,
        # so a credential sitting in a top-level section or an unmerged anchor
        # still fails with nothing named here — which is why the fallback says
        # where else to look rather than "no services".
        culprits = sorted(
            name
            for name, body in services_of(document).items()
            if name != CREDENTIAL_OWNING_SERVICE and bounded & reads(body)
        )
        where = culprits or ["outside any service — a top-level section, or an anchor"]
        problems.append(f"{path.name}: {reached} reaches {where}")

    assert not problems, "\n".join(
        [
            "Something other than the database reads the superuser credential (ADR 0009):",
            *problems,
            "",
            "It does not matter which key it lands in — a connection URL, a build argument, "
            "a label — or how many `.env` entries it came through: the container holds the "
            "password either way, and `db:5432` is reachable from all of them over scram. "
            "That role bypasses every grant, bypasses row-level security, and can run "
            "COPY ... FROM PROGRAM. If this is the migration identity E0-04 needs, ADR 0009 "
            "has a table for who provisions what: amend it, then change "
            "`CREDENTIAL_OWNING_SERVICE` deliberately.",
        ]
    )


def test_only_the_api_service_is_left_holding_the_care_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """`api` keeps the Care connection; every other service that reads `.env` loses it.

    The finding on pull request #29, found independently by two reviewers.
    `CARE_DATABASE_URL` sat on the shared `x-application` anchor, so all three
    application services received the one credential in the cluster that can
    execute `public.reveal_student_identity`. Code execution in `worker` — the
    process that ships student comment text to a third-party model provider — or
    a `docker exec` by an operator holding no `CARE` assignment is then enough:
    read the variable, connect as `pulse_care`, read a live `CARE` assignment out
    of `public.role_assignment`, which that role may `SELECT`, and call the door
    with the borrowed person as the acting actor. It returns a student's name and
    email address, and the audit row names the borrowed Care staffer rather than
    the caller.

    **One half of that has since been closed and this rule is not it.** The
    rollback — a caller keeping the name and leaving no audit row at all, measured
    false on the pinned image against ADR 0042's premise — is closed by E0-26
    item 1: the reveal returns nothing until a separately committed record exists,
    so a caller that rolls back gets no name. What is *not* closed is the borrowing,
    which is E0-26 item 3 and is carried to E10: the acting person is still a
    parameter rather than a property of the connection, so a credential holder can
    still read a real Care staffer's `person_id` and pass it, and the record that
    now reliably survives names that staffer. Possession of this variable is
    therefore still the whole of the exposure, and narrowing who holds it is still
    the control — which is what this test is for.

    **Blanked, not omitted, and that distinction is the whole rule.**
    `env_file: - .env` has already delivered all three variables by the time a
    service's own `environment:` block is applied, so an empty value is what
    removes one and an omitted entry leaves it in place. This is the same shape
    as `DB_SUPERUSER: ''` beside it in the same anchor.

    **All three variables, because the URL alone is not the credential.** The
    pair `DB_CARE_USER` and `DB_CARE_PASSWORD` arrives through the same
    `env_file:`, and `DATABASE_URL` supplies the host, the port and the database
    name, so a process holding the pair assembles the connection in one line. The
    parts are required to be blanked on `api` too — it holds the assembled URL
    and has no use for them — which is what `.env.example` says and what makes
    the rule "no application container holds the parts" rather than "no
    application container except one".

    **Both directions, because either half alone is satisfiable by an accident.**
    A stack that blanks the variable everywhere passes any rule that only forbids
    a value on the other services, and it also breaks the Care queue outright —
    E0-10 makes the Care path a requirement rather than an oversight, and §6.2's
    queue going silently unavailable is the failure ADR 0042 spent an alternative
    on. So `api` is asserted to hold something, and the rest to hold nothing.

    **Over the services that inherit `.env`, not over a list of names**, which is
    the shape ADR 0009's last consequence asks for and the reason the superuser
    rule above is written the same way: a fourth application service copied from
    the anchor arrives blanked, and one written flat with its own `env_file:`
    arrives here as a failure naming itself.

    The base file only. A blank in `docker-compose.override.yml` is absent from
    every deployment that runs the base file alone — which is every real
    deployment, and CI's own base-file-only pass. That asymmetry is stated at
    length on the superuser rule above, and it is the same asymmetry here. The
    other direction, an override that *re-supplies* what the base file blanked,
    belongs to the absolute rule below.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    inheriting = {
        name: body for name, body in services_of(base_compose).items() if declares_env_file(body)
    }

    serving = inheriting.get(CARE_SERVING_SERVICE)
    assert serving is not None, (
        f"No `{CARE_SERVING_SERVICE}` service in docker-compose.yml inherits the whole of "
        "`.env`, so nothing here is handed the Care credential to keep and the assertions "
        "below would be comparing absences. E0-02 ships `api` with `env_file: - .env`."
    )

    serving_url = service_environment(serving).get(CARE_CONNECTION_URL)
    assert serving_url is not None and serving_url.strip(), (
        f"`{CARE_SERVING_SERVICE}` supplies {CARE_CONNECTION_URL} as {serving_url!r}. It is the "
        "one process that serves the §6.2 Care queue, so it is the one process that must hold "
        "this credential — a stack where nobody holds it satisfies every 'the other services "
        "must not hold it' assertion below while the Care queue is dead and nothing says so. "
        "E0-10 makes the Care path a requirement, not an oversight, and ADR 0042 weighs a "
        "silently unavailable queue as the expensive outcome. If `api` has stopped being the "
        "process that serves it, change `CARE_SERVING_SERVICE` deliberately."
    )

    withheld_from: dict[str, tuple[str, ...]] = {
        name: CARE_VARIABLES for name in inheriting if name != CARE_SERVING_SERVICE
    }
    assert withheld_from, (
        "`api` is the only service in docker-compose.yml that inherits the whole of `.env`, so "
        "this rule has nothing left to forbid and passes without checking anything. E0-03 adds "
        "`worker` and `beat` on the same anchor (SPEC §7.2). If the job services now get their "
        "configuration some other way, work out what they are handed and rewrite this rule "
        "around it."
    )
    # `api` keeps the assembled URL and is asked for the parts anyway: it has no
    # use for them, and requiring them here is what stops the rule reading as
    # "every service but one", which is the reading a fourth service inherits.
    withheld_from[CARE_SERVING_SERVICE] = CARE_CREDENTIAL_PARTS

    problems: list[str] = []
    for name, variables in sorted(withheld_from.items()):
        environment = service_environment(inheriting[name])
        for variable in variables:
            if variable not in environment:
                problems.append(
                    f"`{name}` does not blank {variable} at all — `env_file: - .env` has "
                    "already set it, so omitting the entry leaves the value in place"
                )
            elif environment[variable] is None:
                problems.append(
                    f"`{name}` passes {variable} through from the host environment, which is "
                    "where the real credential is"
                )
            elif supplies_a_value(environment[variable]):
                problems.append(f"`{name}` sets {variable} to {environment[variable]!r}")

    assert not problems, "\n".join(
        [
            "An application container is handed a route to the Care credential "
            "(SPEC §6.2, ADR 0042 as amended by E0-10):",
            *problems,
            "",
            "`pulse_care` is the only role in the cluster with EXECUTE on the Care door — "
            "public.record_identity_reveal and public.reveal_student_identity. A caller "
            "holding it can read a live CARE assignment out of role_assignment and borrow "
            "that person as the acting actor, which returns the student's name and email and "
            "leaves a record naming the borrowed staffer (E0-26 item 3, carried to E10). The "
            "rollback half of this — keeping the name and leaving no record at all — is closed "
            "by E0-26 item 1. `worker` and `beat` never serve this queue, and `worker` is "
            "the container that runs E0-13's gateway over untrusted comment text. Blank each "
            "of them in the shared `x-application-environment` anchor: an empty value removes "
            "what `env_file` set, and omitting the entry does not. If a second process "
            "genuinely needs to reveal an identity, that is an amendment to ADR 0042 and a "
            "deliberate edit here.",
        ]
    )


def test_no_compose_file_hands_a_container_the_care_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """Each of the three has exactly one service allowed to carry it, in either file.

    The rule above says a service that inherits the whole of `.env` must take the
    Care credential back out. This one says something simpler and wider: no
    Compose file may *write* one of these three into a container that is not the
    single service entitled to it. The two are complementary — that one is about
    the credential arriving implicitly through `env_file`, this one about it
    being handed over on purpose — and neither implies the other.

    **This is the half that reads the override**, and it is where the superuser
    rules were broken twice. Reviewer pass 2 put `DB_SUPERUSER` on the override's
    `x-development-source` anchor, which is merged into all three application
    services, and delivered the real password to three containers with the whole
    unit suite green. The identical edit is available here: one line on that
    anchor re-supplies `CARE_DATABASE_URL` to `worker` and `beat` while the base
    file goes on blanking it and the rule above goes on passing.

    No merge model is needed for it, which is why this is a question worth asking
    of the override at all. `environment:` beats `env_file:`, and the override's
    `environment:` beats the base file's, so a value written in either file is a
    value the container gets. It over-approximates in the safe direction only.

    **Two owners, not one, and they are different services.** `api` may hold the
    assembled connection because it serves the §6.2 queue. `db` may hold
    `DB_CARE_USER` and `DB_CARE_PASSWORD` because it is the server the role is
    created in, which is the same reason it is the one exemption from the
    superuser rules — and unlike the superuser pair, which it takes under
    Postgres's own names, it takes these two under the names `.env` gives them.
    Neither service is allowed the other's, so `CARE_DATABASE_URL` on `db` or the
    pair on `api` is a failure here even though both are one service away from
    something permitted.

    The canary is the first loop. "Only these two may carry it" is true of a
    stack where nobody carries it, and that stack has no Care queue at all.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. Both Compose files ship, and a file "
            "that did not parse supplies no services — which would narrow this rule silently "
            "rather than fail it."
        )

    assert services_of(override_compose), (
        f"{override_compose_path.name} declares no services, so this test is not reading the "
        "file the override half of this rule is about — the `x-development-source` anchor is "
        "merged into all three application services there, which is one line away from "
        "re-supplying what the base file blanks."
    )

    base_services = services_of(base_compose)
    for variable, owner in sorted(CARE_VARIABLE_OWNERS.items()):
        declared = service_environment(base_services.get(owner) or {}).get(variable)
        assert declared is not None and declared.strip(), (
            f"`{owner}` supplies {variable} as {declared!r} in docker-compose.yml, so nothing "
            "in the stack holds it and the search below would report a clean file for a stack "
            f"with no Care queue in it. `{CARE_SERVING_SERVICE}` serves the §6.2 queue and "
            f"`{CREDENTIAL_OWNING_SERVICE}` is the server the role is created in; if either "
            "has genuinely stopped taking this variable this way, this rule needs rewriting "
            "around whatever replaced it rather than deleting."
        )

    problems: list[str] = []
    for path, document in documents:
        for name, body in sorted(services_of(document).items()):
            environment = service_environment(body)
            for variable, owner in sorted(CARE_VARIABLE_OWNERS.items()):
                if name == owner or variable not in environment:
                    continue
                value = environment[variable]
                if value is None:
                    problems.append(
                        f"{path.name}: `{name}` passes {variable} through from the host "
                        "environment, which is where the real credential is"
                    )
                elif supplies_a_value(value):
                    problems.append(
                        f"{path.name}: `{name}` sets {variable} to {value!r}, and only "
                        f"`{owner}` may carry it"
                    )

    assert not problems, "\n".join(
        [
            "A Compose file hands a container a route to the Care credential "
            "(SPEC §6.2, ADR 0042 as amended by E0-10):",
            *problems,
            "",
            "`pulse_care` is the only role that can execute the Care door, and a caller "
            "holding it can borrow a live CARE assignment out of role_assignment and reveal "
            "under that person's name — E0-26 item 3, carried to E10. Rolling the transaction "
            "back no longer keeps the name: E0-26 item 1 closed that half. It does "
            "not matter which file the value is written in: the override's `environment:` "
            "beats the base file's, and its shared anchor reaches every application service. "
            "Set it to an empty string, or do not name it. If a second process genuinely needs "
            "the Care connection, that is an amendment to ADR 0042 and a change to "
            "`CARE_VARIABLE_OWNERS` made on purpose and reviewed as such.",
        ]
    )


def test_nothing_outside_the_care_and_database_services_reads_the_care_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
    documented_env: dict[str, str],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The Care credential does not reach a container under some other name, or via `.env`.

    The rule above asks whether one of the three is an environment *key*. That is
    one of the ways the value travels and not the only one, and both of the
    others were found by reviewers writing plausible lines against the superuser
    pair — first the credential inside another key's value,

        ALEMBIC_DATABASE_URL: postgresql://${DB_SUPERUSER}:${DB_SUPERUSER_PASSWORD}@db:5432/...

    and then, once that was caught, the same thing one hop further out, with
    `.env.example` assembling the entry the Compose file names. Both put the real
    password into three containers with the suite green. The Care credential is
    open to both spellings exactly as the superuser one was, and E0-19 exists
    because this boundary keeps eroding; `docs/MISTAKES.md` entry 13 is the rule
    that says to close a hazard at every place facing it rather than at the one
    that bit.

    So this is the superuser rule next door with two exemptions instead of one,
    and it is shaped the same way: it reads values rather than keys, it walks
    each document whole with the two exempt service bodies removed — anchors,
    build arguments, labels and top-level sections covered by not being excluded
    — and it resolves names through `.env.example` transitively first, because
    Compose expands `${...}` inside dotenv values and this repository depends on
    that for both URLs.

    `api` is exempt because it serves the queue and `db` because it creates the
    role. The exemption is each service's body and nothing else: an anchor at the
    top level holding the credential is flagged even if only `api` merges it,
    because the top level is one `<<:` away from every service — which is the
    exact shape the fix on pull request #29 uses in the safe direction.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse holds no "
            "interpolations, and a search that finds none reports every file clean."
        )
    assert documented_env, (
        ".env.example is missing or parsed to nothing, so the transitive step below resolves "
        "no names at all and this rule degrades to the one that reviewer pass 4 broke — the "
        "one that sees a URL variable and asks no further."
    )

    values = {name.upper(): value for name, value in documented_env.items()}
    bounded = set(CARE_VARIABLES)

    def reads(node: Any) -> set[str]:
        return transitively_read(node, interpolated_variables_in, values)

    base_services = services_of(base_compose)
    for owner in sorted({CARE_SERVING_SERVICE, CREDENTIAL_OWNING_SERVICE}):
        assert bounded & reads(base_services.get(owner) or {}), (
            f"The `{owner}` service reads none of {sorted(bounded)}, and it is one of the two "
            "that has to. Either the walker is looking at the wrong thing or it is finding "
            "nothing at all, and a rule that finds nothing calls every file clean."
        )

    problems: list[str] = []
    for path, document in documents:
        remainder = document_without(
            document_without(document, CREDENTIAL_OWNING_SERVICE), CARE_SERVING_SERVICE
        )
        reached = sorted(bounded & reads(remainder))
        if not reached:
            continue
        # Attribution for the message only. The assertion is about the document,
        # so a credential sitting in a top-level section or an unmerged anchor
        # still fails with nothing named here — which is why the fallback says
        # where else to look rather than "no services".
        exempt = {CARE_SERVING_SERVICE, CREDENTIAL_OWNING_SERVICE}
        culprits = sorted(
            name
            for name, body in services_of(document).items()
            if name not in exempt and bounded & reads(body)
        )
        where = culprits or ["outside any service — a top-level section, or an anchor"]
        problems.append(f"{path.name}: {reached} reaches {where}")

    assert not problems, "\n".join(
        [
            "Something other than the Care service and the database reads the Care credential "
            "(SPEC §6.2, ADR 0042 as amended by E0-10):",
            *problems,
            "",
            "It does not matter which key it lands in — a second connection URL, a build "
            "argument, a label — or how many `.env` entries it came through: the container "
            "holds a working `pulse_care` connection either way, and that role is the only one "
            "that can execute the audited reveal. `worker` is the process that ships student "
            "comment text to a third-party model provider, which makes it the last container "
            "in the stack that should hold a route to a student's name.",
        ]
    )


def test_neither_compose_file_uses_a_top_level_section_this_module_cannot_read(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """The set of top-level keys is closed, so a new one is a decision and not a slip.

    This is the rule that stops the credential tests being a list of places
    somebody thought of. They walk both parsed documents whole, so they cover
    every section that *is* in these two files — and cover nothing at all about
    a section that moves the configuration somewhere else, or that names a
    variable without interpolating it. Three live examples:

      - `include:` pulls in another Compose file entirely. Nothing in this module
        opens it, so everything below it is unread.
      - a top-level `secrets:` entry can be sourced from `environment:
        DB_SUPERUSER_PASSWORD` — the variable named as a plain value, with no
        `${...}` anywhere, which is invisible to an interpolation walker by
        construction.
      - `configs:` has the same shape as `secrets:`.

    Each was found in a review pass as "the next spelling just past the edge",
    which is why the answer is a closed set rather than a fourth special case.
    Extension fields (`x-…`) stay allowed: they are where the anchors live, they
    are walked like everything else, and Compose gives them no meaning of its
    own.

    Adding a top-level key is therefore a two-part change — the key, and the
    reasoning here for why the credential rules still hold with it. That is the
    intended cost.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. An empty document declares no "
            "top-level keys, and a rule about which keys exist reports nothing wrong when "
            "there are none."
        )

    problems: list[str] = []
    for path, document in documents:
        unreadable = sorted(
            str(key)
            for key in document
            if str(key) not in ALLOWED_TOP_LEVEL_KEYS
            and not str(key).startswith(EXTENSION_FIELD_PREFIX)
        )
        if unreadable:
            problems.append(f"{path.name}: {unreadable}")

    assert not problems, "\n".join(
        [
            "A Compose file declares a top-level section this module has not been taught to "
            "read:",
            *problems,
            "",
            f"Allowed today: {sorted(ALLOWED_TOP_LEVEL_KEYS)}, plus any "
            f"`{EXTENSION_FIELD_PREFIX}` extension field. The credential rules above walk "
            "these documents whole, which makes them complete over what is here and silent "
            "about anything that moves configuration elsewhere or names a variable without "
            "interpolating it — `include:` does the first, `secrets:` and `configs:` do the "
            "second. So this is not a style rule: extend this module to cover the new "
            "section, in the same change that adds it, and then add it to the list.",
        ]
    )


def test_the_repository_root_holds_no_compose_file_this_suite_does_not_read(
    base_compose_path: Path,
    override_compose_path: Path,
) -> None:
    """The set of Compose files is closed, the same way the set of top-level keys is.

    Every rule in this module reads two hand-picked files. Docker does not pick
    them: it looks for the names in `COMPOSE_FILE_NAMES` in its own order of
    precedence, and `compose.yaml` — the modern preferred spelling — beats
    `docker-compose.yml`. Dropping one at the repository root produces

        warning: Found multiple config files with supported names: compose.yaml,
        docker-compose.yml
        warning: Using .../compose.yaml

    measured against the real daemon in reviewer pass 5, with all 76 tests still
    green. `docker-compose.yml` is then read by nobody and every guard written
    for this stack describes a file it no longer runs — the credential rules,
    the health checks, the privilege comparison, the base-file-only pass, all of
    them at once, in one edit that looks like tidying.

    It is the same shape as `include:` and it gets the same answer: a document
    nothing here opens is refused rather than chased. A third file is a decision
    that fails loudly, with this test naming it, instead of a silent redirection
    of the whole stack.

    The expected set comes from the fixtures the rest of the suite reads, not
    from names written down here, so the two cannot drift: whatever this suite
    opens is what Docker must find, and nothing else.

    **The root only, deliberately.** Compose searches its working directory and
    then upwards, never downwards, and every invocation in this repository runs
    from the root — the Makefile, the `docker` job, the `e2e` job. So a Compose
    file in a subdirectory is a different stack (the mock platforms may each get
    one) and is not this rule's business.
    """
    root = base_compose_path.parent
    expected = {base_compose_path.name, override_compose_path.name}

    assert root.is_dir(), (
        f"{root} is not a directory, so the search below looks at nothing and finds "
        "nothing, which this test would otherwise read as 'no stray Compose files'."
    )

    present = {name for name in COMPOSE_FILE_NAMES if (root / name).is_file()}
    unread = sorted(present - expected)
    missing = sorted(expected - present)

    assert present == expected, "\n".join(
        [
            "The Compose files Docker would read are not the ones this suite reads.",
            f"  Docker would also read, and no test opens: {unread or 'none'}",
            f"  This suite reads, and the root does not hold: {missing or 'none'}",
            "",
            "Docker picks by name, in its own order of precedence, and `compose.yaml` wins "
            "over `docker-compose.yml`. So an extra file at the root does not add a stack — "
            "it replaces the one every rule in this module describes, silently, while every "
            "test stays green. If the project is genuinely moving to the modern name, move "
            "it: rename the files and point `tests/fixtures/repo.py` at them, in one change, "
            "so the suite follows the stack. Adding a second base file is not a rename.",
        ]
    )


def test_no_service_uses_extends(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """`extends:` is refused, because it would make the one exemption transitive.

    `db` is exempt from the credential rule above — it is the server that owns
    the role. `extends: {service: db}` on `worker` copies that service's
    environment into `worker`, so the container ends up holding `POSTGRES_USER`
    and `POSTGRES_PASSWORD` with all three credential rules passing: the walker
    sees the interpolation only inside the subtree it was told to skip.

    The cross-file form is worse. `extends: {file: shared.yml, service: base}`
    puts the payload in a document nothing in this module opens, and unlike
    `include:` it does it per service, so it would not even show up as a
    top-level section.

    Nothing here uses it and there is no reason it needs to: two services that
    share configuration share a YAML anchor, which the parser resolves before
    any of these rules run, so an anchor is visible where an `extends` is not.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so it declares no services and this "
            "rule has nothing to disagree with."
        )

    problems = [
        f"{path.name}: `{name}` extends {body['extends']!r}"
        for path, document in documents
        for name, body in sorted(services_of(document).items())
        if "extends" in body
    ]

    assert not problems, "\n".join(
        [
            "A service uses `extends:`, which the credential rules in this module cannot see "
            "through:",
            *problems,
            "",
            f"`extends: {{service: {CREDENTIAL_OWNING_SERVICE}}}` inherits the one service "
            "that is allowed to hold the superuser credential, and the `file:` form points "
            "at a document nothing here parses. Use a YAML anchor instead: the parser "
            "resolves it before any of these rules run, so what a service ends up with is "
            "what they read.",
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


# `dropped_capabilities` used to live here, reading `cap_drop` for the rule that
# compared `worker` and `beat` against `api`: a service dropping fewer
# capabilities than `api` holds more. It went with that comparison in E0-19 —
# see `test_no_service_is_granted_a_privilege_its_image_does_not_carry` for why
# the relative form went, and note that `cap_drop` has no meaning under an
# absolute rule, because there is no baseline to drop fewer than. `cap_drop` is
# not a privilege key and is not refused: dropping capabilities is the safe
# direction, and a service that wants to drop more may.


def normalised_bind_source(source: str, project_directory: Path | str) -> str:
    """One host path, in the one form every comparison in this module is made in.

    **Both sides of every comparison go through here** — the sources read out of
    a Compose file, the entries of `ALLOWED_BIND_MOUNTS`, and
    `SENSITIVE_BIND_SOURCES` — because a comparison is only as good as the
    agreement between its two sides, and a rule that normalises one of them
    rejects a mount that reaches nothing and clears one that reaches the host.

    Two rules, and each was measured rather than reasoned about.

    **A relative source resolves against the project directory**, which is the
    directory the Compose file is in, and never against the service's
    `working_dir`. Measured during E0-03's review with `working_dir: /opt/app`
    on the service: no effect on where the mount came from.

    **Alternate spellings survive into the daemon.** Measured against the local
    Docker daemon on 2026-08-21, by the orchestrating session and not by the
    author of this test. A Compose file declared four spellings of one host
    directory — `./host/./sub`, `//<abs>//host/sub`, `../bindprobe/host/sub`,
    and `<abs>/host//sub`. In `docker compose config` output the `.`-segment
    relative source came back resolved and collapsed and the `..` source
    resolved against the project directory, while `///<abs>//host/sub` and
    `<abs>/host//sub` survived with their doubled separators verbatim. All four
    mounted, and the container read the host's marker file through every one. So
    the alternate spellings reach the host, and because this module parses the
    raw YAML rather than `docker compose config` output, the collapsing has to
    happen here.

    **Purely textual: no filesystem access, no symlink resolution, no `~`
    expansion.** `Path.resolve()` would answer differently depending on what
    happens to exist on the machine running the tests, which is not a property
    of the Compose file, and it would make the test's answer depend on a
    developer's checkout. A `~` source and a `${HOST_DIR}` source therefore
    normalise to something no allowlist entry matches, and are refused — the
    safe direction, and the reason nothing here tries to be clever about them.

    The leading-double-slash case is explicit and is not decoration:
    `posixpath.normpath` preserves *exactly two* leading slashes, because POSIX
    leaves their meaning implementation-defined, so `//var/run/docker.sock`
    comes back out of `normpath` unchanged and compares unequal to
    `/var/run/docker.sock`. That is one of the two spellings measured above.
    """
    text = str(source).strip()
    if not text:
        return ""
    if not text.startswith("/"):
        text = f"{str(project_directory).rstrip('/')}/{text}"
    collapsed = posixpath.normpath(text)
    # `normpath` keeps exactly two leading slashes and collapses three or more,
    # so this is the one case it will not do for us.
    if collapsed.startswith("/"):
        return "/" + collapsed.lstrip("/")
    return collapsed


class BindMounts(NamedTuple):
    """What a service reaches on the host, and what this module could not read.

    `unreadable` is the half that makes the closed set closed. A declaration
    this module cannot classify contributes no source, and a rule phrased over
    sources alone would read that as a service mounting nothing — which is the
    outcome the whole strategy exists to prevent. Carried separately so that it
    can be a failure rather than a silence.
    """

    sources: frozenset[str]
    unreadable: tuple[str, ...]


def top_level_volumes(document: dict[str, Any]) -> dict[str, Any]:
    """The `volumes:` section of one Compose file, keyed by name.

    A section that is not a mapping yields nothing, which makes every named
    volume in the file unresolvable and therefore refused below. That is the
    safe direction: a `volumes:` section this module cannot read is not a file
    whose named volumes are all harmless.

    One file, and this is not what the rules read — `merged_volume_bodies` is.
    See its docstring for why reading one file was a hole rather than a
    simplification.
    """
    declared = document.get("volumes")
    if not isinstance(declared, dict):
        return {}
    return {str(name): body for name, body in declared.items()}


def merged_body(under: Any, over: Any) -> Any:
    """Two declarations of one thing, combined the way Compose combines them.

    Mappings merge key by key and recursively; anything else is replaced by the
    later file, and a later file that says nothing (`beat-schedule:` with an
    empty body) leaves the earlier declaration standing. That is Compose's rule
    for a mapping, and it is the rule that matters here because a volume body is
    a mapping.

    Where the merge is genuinely ambiguous the result lands in the
    unclassifiable branch of `named_volume_source`, which refuses — so getting
    an unusual combination slightly wrong fails closed rather than open.
    """
    if isinstance(under, dict) and isinstance(over, dict):
        combined = dict(under)
        for key, value in over.items():
            combined[key] = merged_body(combined.get(key), value) if key in combined else value
        return combined
    return under if over is None else over


def merged_volume_bodies(documents: ComposeDocuments) -> dict[str, Any]:
    """The top-level `volumes:` section as Docker assembles it, across every file.

    **This is the fix for E0-19's second security review, and the hole it closes
    was measured against the daemon.** Every mount rule here used to resolve a
    named volume in the *same document* as the service that mounts it, on the
    reasoning that this module reads the two files one at a time and refuses to
    model Compose's merge. That reasoning is right about services and wrong
    about this section: `docker compose up` merges the top-level `volumes:`
    across both files before any service mounts anything, so the override can
    redefine a volume the base file mounts.

    `beat` mounts `beat-schedule`, which the base file declares with an empty
    body. Adding

        volumes:
          beat-schedule:
            driver_opts: {type: none, device: /, o: bind}

    to `docker-compose.override.yml` — or `beat-schedule: {name: precreated-host-root}`
    — gives that container the host root. Measured: 460 tests green, and the
    running container read the host's `.env` through the mount. Per-file
    resolution saw the base file's empty body and called it an ordinary Docker
    volume; nothing looked at the override, because nothing mounted anything
    there.

    So the merge is done here, once, and every rule that consumes a resolved
    volume reads the result: the allowlist, the sensitive check, and the
    `name:`/`driver:` refusal. The asymmetry between the two files is still
    load-bearing everywhere else in this module — what a service may *mount* is
    keyed by the file that declares the mount — and it is not load-bearing here,
    because a volume body is not per-file configuration in the first place.
    """
    merged: dict[str, Any] = {}
    for _, document in documents:
        for name, body in top_level_volumes(document).items():
            merged[name] = merged_body(merged.get(name), body) if name in merged else body
    return merged


def named_volume_source(
    name: str,
    volumes: dict[str, Any],
    project_directory: Path | str,
) -> tuple[str | None, str | None]:
    """What host path a named volume resolves to, or why this module cannot say.

    Returns a `(source, refusal)` pair with at most one of them set. A volume
    that is genuinely not a bind — the ordinary local volume `beat-schedule` and
    `postgres-data` are both this — sets neither: it names no host path, and
    saying so is not a refusal.

    E0-19's second route. `driver_opts: {type: none, device: /var/run/docker.sock,
    o: bind}` is a bind mount with a name in front of it, and the service entry
    that mounts it says only `- host-root:/host`. The docker socket is root on
    the host, and `worker` is the container E0-13 runs untrusted comment text
    through.

    Everything this module has not been taught to read is refused rather than
    treated as harmless — an `external: true` volume is created somewhere this
    file cannot see, and an `nfs` device is a path on another machine. Both are
    features this repository does not use, and the ticket's own rule is that a
    feature stays refused rather than modelled.

    `name:` and `driver:` join `external:` in that refusal, and E0-19's security
    review is why. They were admitted here as metadata and returned "not a bind,
    not a refusal", which is the worst of the three answers: a `name:` attaches
    the volume to a pre-created Docker volume under that exact name with no
    project prefix, and one `docker volume create --opt device=/ --opt o=bind`
    beforehand makes the innocuous-looking entry a mount of the host root. See
    `VOLUME_KEYS_NAMING_SOMETHING_ELSE`.

    `volumes` is the **merged** top-level section, across every Compose file —
    never one document's. `merged_volume_bodies` says why, and the short version
    is that a body read from one file is not the body the daemon uses.
    """
    if name not in volumes:
        return None, (
            f"names the volume `{name}`, which no Compose file's top-level `volumes:` section "
            "declares, so what it mounts cannot be read here"
        )

    body = volumes[name]
    if body is None or body == {}:
        return None, None
    if not isinstance(body, dict):
        return None, f"declares the volume `{name}` as {body!r}, which this module cannot read"

    elsewhere = sorted(str(key) for key in body if str(key) in VOLUME_KEYS_NAMING_SOMETHING_ELSE)
    if elsewhere:
        return None, (
            f"declares the volume `{name}` with {elsewhere}, which says the volume is defined "
            "somewhere this file cannot see — a pre-created Docker volume under that exact "
            "name, or a plugin that decides what it is — so what it mounts cannot be read here"
        )

    unknown = sorted(str(key) for key in body if str(key) not in READABLE_VOLUME_KEYS)
    if unknown:
        return None, (
            f"declares the volume `{name}` with {unknown}, which this module has not been "
            f"taught to read (it reads {list(READABLE_VOLUME_KEYS)})"
        )

    options = body.get("driver_opts")
    if options is None:
        return None, None
    if not isinstance(options, dict):
        return (
            None,
            f"declares the volume `{name}` with driver_opts {options!r}, which is not a mapping",
        )

    device = options.get("device")
    if device is None:
        return None, (
            f"declares the volume `{name}` with driver_opts {dict(options)!r} and no `device:`, "
            "so this module cannot say what it mounts"
        )

    declared_type = str(options.get("type") or "").strip().lower()
    flags = {flag.strip().lower() for flag in str(options.get("o") or "").split(",")}
    if declared_type in BIND_DEVICE_TYPES or BIND_DEVICE_FLAG in flags:
        return normalised_bind_source(str(device), project_directory), None

    return None, (
        f"declares the volume `{name}` with driver_opts {dict(options)!r}, a `device:` this "
        "module cannot classify as a bind or as anything else"
    )


def bind_mounts_of(
    service: dict[str, Any],
    volumes: dict[str, Any],
    project_directory: Path | str,
) -> BindMounts:
    """Every host path this service reaches, in every spelling Compose allows.

    Supersedes the E0-03 reader that looked only at service-level entries whose
    source began with `/`, `.` or `~`. Three things changed and all three were
    routes past it: sources are normalised (see `normalised_bind_source`), a
    named volume is resolved through the top-level `volumes:` section rather
    than assumed harmless, and a declaration this module cannot classify is
    carried out as a refusal instead of contributing nothing.

    **`volumes` is the merged top-level section across every Compose file**, and
    this parameter used to be the one document the service was declared in. That
    was a hole rather than a simplification, it was measured against the daemon,
    and `merged_volume_bodies` carries the measurement: Docker merges this
    section before any service mounts anything, so a volume body written in the
    override is the body a base-file service gets. Nothing else in this module
    merges anything, and the reason this section does is that a volume body was
    never per-file configuration.
    """
    sources: set[str] = set()
    unreadable: list[str] = []

    for entry in service.get("volumes") or []:
        declared_type: Any = None
        source: Any = None

        if isinstance(entry, dict):
            declared_type = entry.get("type")
            source = entry.get("source")
        elif isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) == 1:
                # An anonymous volume: a container path and no host path at all.
                continue
            source = parts[0]
        else:
            unreadable.append(f"declares the volume entry {entry!r}, which this module cannot read")
            continue

        kind = None if declared_type is None else str(declared_type).strip().lower()
        if kind is not None and kind not in (
            BIND_MOUNT_TYPE,
            VOLUME_MOUNT_TYPE,
            *HOSTLESS_MOUNT_TYPES,
        ):
            unreadable.append(
                f"declares a volume of type {declared_type!r}, which this module has not been "
                "taught to read"
            )
            continue
        if kind in HOSTLESS_MOUNT_TYPES:
            continue

        if not isinstance(source, str) or not source.strip():
            if kind == VOLUME_MOUNT_TYPE:
                # An anonymous volume in the long form. No host path exists.
                continue
            unreadable.append(
                f"declares the volume entry {entry!r}, which names no source this module can read"
            )
            continue

        source = source.strip()
        if kind == BIND_MOUNT_TYPE or (kind is None and source.startswith(HOST_PATH_PREFIXES)):
            sources.add(normalised_bind_source(source, project_directory))
            continue

        resolved, refusal = named_volume_source(source, volumes, project_directory)
        if refusal is not None:
            unreadable.append(refusal)
        elif resolved:
            sources.add(resolved)

    return BindMounts(sources=frozenset(sources), unreadable=tuple(unreadable))


# `bind_sources` used to sit here — the E0-03 reader, kept through E0-19 as a
# one-line wrapper over `bind_mounts_of` so that the privilege comparison could
# go on calling it by its old name. That comparison went absolute in E0-19's fix
# round and stopped reading mounts at all, which left this with no caller. It is
# gone rather than kept: a helper nothing calls is a helper nothing notices
# breaking, and its docstring had already begun claiming a set of consumers that
# was one rule out of date. Everything reads `bind_mounts_of` through
# `declared_bind_mounts` now, which is the single reader the ticket's "or a
# sibling it feeds" asks for.


def declared_bind_mounts(documents: ComposeDocuments) -> dict[tuple[str, str], BindMounts]:
    """Every service's resolved host mounts, keyed by (file name, service name).

    **Takes every Compose file rather than one**, and that is E0-19's second
    security review in one signature. A service's mounts are still read from the
    file that declares them — that asymmetry is what `ALLOWED_BIND_MOUNTS` is
    keyed by — but the volume bodies those mounts resolve through are merged
    across all of them, because Docker merges that section before a service
    mounts anything. Passing one file used to be possible and was the hole; now
    the merged table cannot be forgotten at a call site, because there is no call
    site that assembles it.

    The project directory is each file's own `path.parent`, so a relative source
    resolves against the directory of the file it was written in — which is what
    Compose does.
    """
    volumes = merged_volume_bodies(documents)
    return {
        (path.name, name): bind_mounts_of(body, volumes, path.parent)
        for path, document in documents
        for name, body in services_of(document).items()
    }


def unallowlisted_bind_mounts(documents: ComposeDocuments) -> list[str]:
    """Mounts that `ALLOWED_BIND_MOUNTS` does not permit, one per line.

    A mount of the project directory, or of any ancestor of it, carries the
    reason that particular one is fatal: `.env` lives beside the Compose file,
    because `env_file: - .env` requires it, so mounting the directory hands the
    container the superuser credential the `environment:` block blanked.
    """
    directories = {path.name: path.parent for path, _ in documents}
    problems: list[str] = []

    for (file_name, name), mounts in sorted(declared_bind_mounts(documents).items()):
        directory = directories[file_name]
        project = normalised_bind_source(".", directory)
        allowed = {
            normalised_bind_source(entry, directory)
            for entry in ALLOWED_BIND_MOUNTS.get((file_name, name), frozenset())
        }
        for source in sorted(mounts.sources - allowed):
            note = ""
            # `rstrip` so that the root is an ancestor of everything: `/` and `/`
            # concatenated is `//`, which nothing starts with.
            if source == project or project.startswith(f"{source.rstrip('/')}/"):
                note = (
                    " — and .env lives in the project directory, so this mount hands the "
                    "container the whole file that the `environment:` block blanks the "
                    "superuser pair out of"
                )
            permitted = sorted(allowed) or "nothing"
            problems.append(
                f"{file_name}: `{name}` bind-mounts {source}, which is not in its allowlist "
                f"({permitted}){note}"
            )

    return problems


def sensitive_bind_mounts(documents: ComposeDocuments) -> list[str]:
    """Mounts whose source is on `SENSITIVE_BIND_SOURCES`, one per line.

    Defence in depth behind the allowlist rather than a second copy of it: a
    path that somehow enters the allowlist — a fifth entry added in a hurry,
    a review that read the entry and not the path — still fails here by name.
    Both checks read the same resolved, normalised set, so neither can be true
    of a spelling the other misses.
    """
    problems: list[str] = []
    directories = {path.name: path.parent for path, _ in documents}

    for (file_name, name), mounts in sorted(declared_bind_mounts(documents).items()):
        forbidden = {
            normalised_bind_source(entry, directories[file_name]): entry
            for entry in SENSITIVE_BIND_SOURCES
        }
        for source in sorted(mounts.sources & set(forbidden)):
            problems.append(
                f"{file_name}: `{name}` bind-mounts {source}, which is "
                f"{forbidden[source]!r} on the sensitive list"
            )

    return problems


def unreadable_volume_declarations(documents: ComposeDocuments) -> list[str]:
    """Volume declarations the reader above could not classify, one per line."""
    return [
        f"{file_name}: `{name}` {note}"
        for (file_name, name), mounts in sorted(declared_bind_mounts(documents).items())
        for note in mounts.unreadable
    ]


def service_keys_of(document: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """What each service in this file declares, keyed by service name.

    The keys as the parser hands them over, which is **after** PyYAML has
    resolved the `<<:` merges: `api` declares `build`, `env_file` and
    `environment` here although none of the three is written in its block, and
    that is the form every rule in this module reads. A reader built from the
    lines visible in the file would be blind to exactly the anchor that has
    twice been the route a credential took.
    """
    return {
        name: tuple(sorted(str(key) for key in body))
        for name, body in services_of(document).items()
    }


def unreadable_service_keys(path: Path, document: dict[str, Any]) -> list[str]:
    """Service keys in this file that are not in `ALLOWED_SERVICE_KEYS`, one per line.

    The closed set one level in from `ALLOWED_TOP_LEVEL_KEYS`, and it exists
    because that one bounds the *sections* a file may declare and says nothing
    about what a service body may carry. `volumes_from: - db` is the
    measurement: every mount `db` has, granted to `worker`, with the whole suite
    green because the mount rules read `volumes:` and there is nothing to read.
    """
    problems: list[str] = []
    for name, keys in sorted(service_keys_of(document).items()):
        for key in keys:
            if key not in ALLOWED_SERVICE_KEYS:
                problems.append(f"{path.name}: `{name}` declares `{key}:`")
    return problems


def build_keys_of(document: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """What each service's `build:` section declares, keyed by service name.

    A service that declares no `build:` is absent. A `build:` written as a bare
    context string has no sub-keys and reports an empty tuple, which is not the
    same as being absent and is why the two are distinguished: it is a build
    this rule has nothing to object to, rather than no build.
    """
    found: dict[str, tuple[str, ...]] = {}
    for name, body in services_of(document).items():
        declared = body.get("build")
        if isinstance(declared, dict):
            found[name] = tuple(sorted(str(key) for key in declared))
        elif isinstance(declared, str) and declared:
            found[name] = ()
    return found


def unreadable_build_keys(path: Path, document: dict[str, Any]) -> list[str]:
    """`build:` sub-keys outside `ALLOWED_BUILD_KEYS`, one per line.

    The service-level closed set said which keys a service may declare and said
    nothing about what an allowed key may carry — which is the same sentence the
    top-level closed set earned when `volumes:` turned out to be a container for
    `driver_opts`. `build:` is the second place that shape appeared, and
    `additional_contexts` is the sharp one: a second context, outside the
    project directory and outside `.dockerignore`, read by a `COPY --from` at
    build time.
    """
    problems: list[str] = []
    for name, keys in sorted(build_keys_of(document).items()):
        for key in keys:
            if key not in ALLOWED_BUILD_KEYS:
                problems.append(f"{path.name}: `{name}` declares `build.{key}:`")
    return problems


class PublishedPort(NamedTuple):
    """One `ports:` entry: the host address it binds, and how it was written."""

    host_ip: str | None
    spelling: str


def published_ports(service: dict[str, Any]) -> list[PublishedPort]:
    """Every port this service publishes to the host, with the address it binds.

    `host_ports_published_by` above answers "is a fixed host port declared",
    which is what the base file's no-publishing rule needs. This answers a
    different question — *where* — and keeps the entry as written so a failure
    can quote the line.

    Every spelling Compose accepts:

      - `"8000"`, which publishes on an ephemeral host port on **every**
        interface, and so binds no address;
      - `"8000:8000"`, the same for a fixed port;
      - `"127.0.0.1:8000:8000"`, which binds one;
      - `"[::1]:8000:8000"`, the same in IPv6, where the brackets are what stop
        the address being split on its own colons;
      - the long form `{target: 8000, published: 8000, host_ip: 127.0.0.1}`.

    A `/tcp` or `/udp` suffix is stripped first; it says nothing about the
    address. A long-form entry with no `published:` still publishes — the daemon
    picks the host port — so it is returned rather than skipped, and its
    `host_ip` decides it like every other.
    """
    found: list[PublishedPort] = []

    for entry in service.get("ports") or []:
        if isinstance(entry, dict):
            declared_ip = entry.get("host_ip")
            found.append(
                PublishedPort(
                    host_ip=None if declared_ip is None else str(declared_ip),
                    spelling=repr(dict(entry)),
                )
            )
            continue

        text = str(entry).rsplit("/", 1)[0]
        host_ip: str | None = None
        if text.startswith("["):
            closing = text.find("]")
            if closing != -1:
                host_ip = text[1:closing]
                text = text[closing + 1 :].lstrip(":")
        parts = text.split(":")
        if host_ip is None and len(parts) >= 3:
            host_ip = parts[0]
        found.append(PublishedPort(host_ip=host_ip, spelling=str(entry)))

    return found


def non_loopback_publications(path: Path, document: dict[str, Any]) -> list[str]:
    """Published ports that bind something other than loopback, one per line."""
    problems: list[str] = []
    for name, body in sorted(services_of(document).items()):
        for port in published_ports(body):
            if port.host_ip in LOOPBACK_HOST_IPS:
                continue
            where = f"on {port.host_ip}" if port.host_ip else "on every interface"
            problems.append(f"{path.name}: `{name}` publishes {port.spelling} {where}")
    return problems


def privilege_grants(path: Path, document: dict[str, Any]) -> list[str]:
    """Privilege keys declared in this file that no exception excuses, one per line.

    Absolute rather than relative, and `ALLOWED_PRIVILEGE_GRANTS` carries the
    exceptions. The reason the comparison against `api` went is recorded on the
    test below and in this module's docstring: the shared anchor grants all
    three application services at once, so the relative form compares a service
    with itself.

    `privilege_declarations` still does the normalising, so `privileged: false`
    and an empty `cap_add` are not grants — a key that hands over nothing is not
    a key to argue about.
    """
    problems: list[str] = []
    for name, body in sorted(services_of(document).items()):
        for key, value in sorted(privilege_declarations(body).items()):
            if (path.name, name, key) in ALLOWED_PRIVILEGE_GRANTS:
                continue
            problems.append(f"{path.name}: `{name}` declares `{key}: {value!r}`")
    return problems


def service_strings(node: Any) -> list[str]:
    """Every string anywhere inside a parsed service body, keys included.

    Recursive because the value being looked for does not care how deeply it is
    nested: `healthcheck.test` is a list, `build.args` is a mapping inside a
    mapping, and `labels` can be either. Keys are walked as well as values,
    because a mapping key is a string somebody can write a credential into and
    reading only values would be the same enumeration mistake one layer down.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [
            text
            for key, value in node.items()
            for text in [*service_strings(key), *service_strings(value)]
        ]
    if isinstance(node, list):
        return [text for item in node for text in service_strings(item)]
    return []


def credential_literals(
    path: Path,
    document: dict[str, Any],
    credentials: tuple[tuple[str, str], ...],
) -> list[str]:
    """Services in this file with a credential written into a string, one per line.

    The rules above this one follow `${...}` references, so they see
    `${DB_SUPERUSER}` wherever it is written and see nothing at all when the
    value is typed out instead. E0-19's security review measured that: the
    superuser URL spelled out in `worker`'s `command:`, suite green.
    `command:`, `entrypoint:`, `healthcheck.test`, `labels:` and `build.args`
    are all strings that reach a container, and none of them is an
    `environment:` entry.

    **Every service, `db` included.** The exemption `db` holds is from *reading*
    the credential — it takes it by interpolation, which is how a deployment's
    real `.env` reaches Postgres. A literal is a different thing: it is the
    placeholder from `.env.example` committed into a Compose file, which is a
    credential in the repository whatever service it is on.

    A `${...}` reference is a name rather than a value and stays green here,
    which is why this searches for the resolved value and never for the
    variable's name.
    """
    problems: list[str] = []
    for name, body in sorted(services_of(document).items()):
        for text in service_strings(body):
            for label, secret in credentials:
                if secret and secret in text:
                    problems.append(f"{path.name}: `{name}` writes {label} into {text!r}")
    return problems


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


def test_no_service_is_granted_a_privilege_its_image_does_not_carry(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """E0-03's security review, restated absolutely after E0-19's defeated the old form.

    Sharing the image settles what is *inside* the container. It settles nothing
    about what Compose grants around it, and that is where privilege is actually
    handed out: `privileged: true`, a `user: root` that overrides the image's
    non-root user, an added capability, a relaxed seccomp profile, the host PID
    namespace. Each of those makes the stack come up exactly as it did before,
    so criterion 1, the health gate and the round-trip test all stay green —
    `docs/MISTAKES.md` entry 2, where the guard is the thing with nothing
    asserting it.

    **This was a comparison against `api` until E0-19, and the reason it is not
    one now is a measurement rather than a preference.** The argument for the
    relative form was good: a privilege the whole stack legitimately gains later
    should not have to be granted twice, and a rule phrased as "no more than
    `api`" cannot be satisfied by granting it to `api` quietly, since `api` is
    the service E0-02 checks the uid of on the running container. What it missed
    is that "granting it to `api` quietly" is *one line*. The override's
    `x-development-source` anchor is merged into `api`, `worker` and `beat`, so
    a privilege written there is held by all three and the comparison is between
    a service and itself. E0-19's security review ran it: `privileged: true`,
    `pid: host`, `network_mode: host`, `userns_mode: host`, a `devices` entry
    and `cap_add: [SYS_ADMIN]`, each added to that anchor, each granting all
    three application services the host, and every one of them green against the
    whole suite. The same anchor was the route reviewer pass 2 used to put the
    superuser password into three containers, which is the second time one line
    in a shared anchor has defeated a rule phrased per service.

    So the rule is absolute: **no service declares a privilege key at all**,
    unless `ALLOWED_PRIVILEGE_GRANTS` names the file, the service and the key
    and says why. That structure is empty today, and the exception it would hold
    has to be argued in a diff rather than inherited from an anchor.

    Both files, because the anchor that defeated the old rule lives in the
    override and a grant in either file is a grant some container holds.

    Two things the old comparison did that this does not, said plainly rather
    than dropped in silence. It compared `cap_drop` — a service dropping fewer
    capabilities than `api` holds more — which is a comparison between two
    services that both drop nothing today, and under an absolute rule there is
    no baseline to drop fewer than. And it compared bind mounts, which moved to
    `test_no_service_bind_mounts_a_sensitive_host_path` and
    `test_no_service_bind_mounts_a_host_path_outside_the_allowlist`: both are
    absolute, both read the resolved sources, and both are strictly stronger
    than "more than `api` has".
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse declares no "
            "services, and a rule about what services declare reports it clean."
        )
    assert PRIVILEGE_KEYS, (
        "PRIVILEGE_KEYS is empty, so this rule forbids nothing and passes over any file at "
        "all. The list is the test's choice and is meant to grow."
    )

    problems = [
        problem for path, document in documents for problem in privilege_grants(path, document)
    ]

    assert not problems, "\n".join(
        [
            "A service is granted privilege beyond what its image carries:",
            *problems,
            "",
            "Nothing dynamic checks this: the stack comes up healthy either way, and a grant "
            "written on the shared `x-development-source` anchor reaches `api`, `worker` and "
            "`beat` at once — which is how the comparison this rule replaced was defeated. "
            "`worker` is the container that will run E0-13's gateway over untrusted comment "
            "text. If the grant is genuinely needed, add an entry to ALLOWED_PRIVILEGE_GRANTS "
            "naming the file, the service and the key, with the reason as its value, and say "
            "in the pull request what the container can now reach.",
        ]
    )


def test_the_privilege_exceptions_excuse_only_grants_that_exist(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """An exception outlives the grant it was written for unless something says otherwise.

    The pair to the rule above, and the same shape as
    `test_the_allowlist_permits_no_mount_the_compose_files_do_not_declare`: a
    permission left behind by a removed grant is inherited by whatever is
    written under that name next, and nobody re-reads it.

    **Vacuous today, deliberately and visibly.** `ALLOWED_PRIVILEGE_GRANTS` is
    empty, so this iterates nothing; its value arrives with the first entry, and
    it is here now so that the first entry cannot be added without it. That is
    the opposite of the usual reason to distrust an empty assertion — the rule
    above is the one that would go quiet on an empty subject, and it asserts
    `PRIVILEGE_KEYS` is non-empty for exactly that reason.
    """
    documents = {
        base_compose_path.name: base_compose,
        override_compose_path.name: override_compose,
    }

    problems: list[str] = []
    for (file_name, service_name, key), reason in sorted(ALLOWED_PRIVILEGE_GRANTS.items()):
        if not str(reason).strip():
            problems.append(f"({file_name}, {service_name}, {key}) carries no reason")
        if file_name not in documents:
            problems.append(
                f"({file_name}, {service_name}, {key}) names a Compose file this suite does "
                "not read"
            )
            continue
        body = services_of(documents[file_name]).get(service_name)
        if body is None:
            problems.append(f"{file_name} declares no `{service_name}` service")
            continue
        if key not in privilege_declarations(body):
            problems.append(
                f"{file_name}: `{service_name}` does not declare `{key}:`, so the exception "
                "excuses nothing and is a standing permission"
            )

    assert not problems, "\n".join(
        [
            "ALLOWED_PRIVILEGE_GRANTS excuses a grant that is not there:",
            *problems,
            "",
            "An exception is written for a grant, in the change that adds the grant, and comes "
            "out in the change that removes it. One that outlives its grant is a permission "
            "waiting for the next service to be given that name.",
        ]
    )


# ---------------------------------------------------------------------------
# What a container reaches on the host — ticket E0-19.
#
# Four routes to ADR 0009's bound, all of them green against the whole suite
# when they were found in E0-03's fifth reviewer pass, and all four answered by
# one shape: an allowlist of normalised sources, keyed by file and service, with
# the denylist kept behind it.
#
# The rules below come in pairs on purpose. A rule that only ever refuses can be
# satisfied by a reader that finds nothing, and a reader that finds everything
# can be satisfied by a rule that refuses nothing, so each rule is written
# against a document that must fail it *and* a document that must pass — and the
# reader itself is required to find a mount in every currency one can be
# declared in (`docs/MISTAKES.md` entry 35).
#
# The documents these boundary tests use are written here rather than read from
# the repository, because the property under test is what the rule does with a
# mount the repository does not contain. They go through the same functions the
# real files do, from the file-level entry point down, so a resolution step that
# stops being called fails these too.
# ---------------------------------------------------------------------------

# Where the sample documents below pretend to live. Nothing on disk: these paths
# are textual, and the normaliser reads no filesystem. The file *names* matter
# and are checked against the real ones by a test below, because
# `ALLOWED_BIND_MOUNTS` is keyed by them — a sample keyed to a name the project
# no longer uses would find an empty allowlist and pass every refusal test for
# the wrong reason.
SAMPLE_PROJECT_DIRECTORY = Path("/srv/pulse")
SAMPLE_BASE_PATH = SAMPLE_PROJECT_DIRECTORY / "docker-compose.yml"
SAMPLE_OVERRIDE_PATH = SAMPLE_PROJECT_DIRECTORY / "docker-compose.override.yml"

# The two credential values as literals, for the sample documents below only.
# The rule over the real files reads them out of `.env.example` — that is the
# file CI copies to `.env`, so the placeholder there is the string that must not
# appear in a Compose file. A sample doing the same would assert against
# whatever the placeholder happens to be and would go quiet the day somebody
# changed it, which is the opposite of what a sample is for.
SAMPLE_SUPERUSER_LITERALS = (
    ("the superuser role name", "pulse_admin"),
    ("the superuser password", "replace-me-admin"),
)


def one_compose_file(path: Path, document: dict[str, Any]) -> ComposeDocuments:
    """A stack of exactly one file, for a boundary test whose subject is in that file.

    Spelled out at every call site rather than defaulted, because after E0-19's
    second security review the number of files is part of what the mount rules
    read: volume bodies are merged across all of them, and a test that hands
    over one file is asserting about a stack that has one. The tests for the
    cross-file merge hand over two.
    """
    return ((path, document),)


def sample_document(
    service_name: str,
    volumes: list[Any],
    top_level: dict[str, Any] | None = None,
    extra_services: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A Compose document with one service mounting `volumes`, and nothing else in it."""
    services: dict[str, Any] = {service_name: {"volumes": volumes}}
    services.update(extra_services or {})
    document: dict[str, Any] = {"services": services}
    if top_level is not None:
        document["volumes"] = top_level
    return document


class BindCurrencySample(NamedTuple):
    """One way of declaring a host mount, and the host path it must resolve to."""

    currency: str
    entry: Any
    volumes: dict[str, Any]
    expected: str


# One sample per currency in `BIND_DECLARATION_CURRENCIES`, each written so that
# **only its own mechanism can catch it** — the `type: none` volume carries an
# `o:` with no `bind` in it, and the `o: bind` volume declares no `type:` at all.
# Written that way because a sample two mechanisms both catch keeps the control
# green when one of them is deleted, which is the shape E0-34's review found
# (`docs/MISTAKES.md` entry 35).
BIND_CURRENCY_SAMPLES = (
    BindCurrencySample(
        currency="short form, relative source",
        entry="./scripts/db-init:/docker-entrypoint-initdb.d:ro",
        volumes={},
        expected="/srv/pulse/scripts/db-init",
    ),
    BindCurrencySample(
        currency="short form, absolute source",
        entry="/var/run/docker.sock:/var/run/docker.sock",
        volumes={},
        expected="/var/run/docker.sock",
    ),
    BindCurrencySample(
        currency="long form, type bind",
        entry={"type": "bind", "source": "/etc", "target": "/host/etc", "read_only": True},
        volumes={},
        expected="/etc",
    ),
    BindCurrencySample(
        currency="long form, no type",
        entry={"source": "./backend", "target": "/app/backend"},
        volumes={},
        expected="/srv/pulse/backend",
    ),
    BindCurrencySample(
        currency="named volume, driver_opts type none",
        entry="host-state:/state",
        volumes={
            # No `driver: local` beside it, although that is how the shape is
            # usually written: E0-19's security review moved `driver:` into the
            # refused set, so a sample carrying one would be refused before it
            # reached the classifier this sample exists to exercise.
            "host-state": {
                "driver_opts": {"type": "none", "device": "/var/lib/pulse", "o": "rw"},
            }
        },
        expected="/var/lib/pulse",
    ),
    BindCurrencySample(
        currency="named volume, driver_opts o flags",
        entry="host-socket:/var/run/docker.sock",
        volumes={
            "host-socket": {
                "driver_opts": {"device": "/var/run/docker.sock", "o": "rw,bind"},
            }
        },
        expected="/var/run/docker.sock",
    ),
)


def test_no_service_bind_mounts_a_host_path_outside_the_allowlist(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """E0-19 route 1: what each service may mount is a closed set, per file.

    The mutation this must kill is one line — `- ./:/app/repo:ro` on `worker`,
    `beat` or `api` in either file, which is what someone writes to get
    `alembic/` or `scripts/` into the job container. It passed every test in
    this module before E0-19 while handing that container the whole of `.env`:
    the file sits beside `docker-compose.yml` in every deployment because
    `env_file: - .env` requires it, so the two blanking lines the anchor writes
    are undone by a mount of the directory they live in.

    The near misses matter more than that one, and each is a test below: a mount
    one path segment away from an allowed source (`./backend2` where `./backend`
    is allowed, `./scripts` where `./scripts/db-init` is), an allowed source
    mounted by a service that has no entry, the same host path spelled with a
    `.` segment or a doubled separator, and the same host path reached through a
    named volume's `driver_opts`.

    Both files, because a mount in either is a mount some container gets — the
    same reason the absolute credential rules read both. Which file is not
    incidental: `ALLOWED_BIND_MOUNTS` is keyed by it, and the asymmetry is
    stated there.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse declares no "
            "services and no mounts, and a rule about what is mounted reports every file clean."
        )

    problems = unallowlisted_bind_mounts(documents)

    assert not problems, "\n".join(
        [
            "A service bind-mounts a host path its allowlist does not permit (ADR 0009, E0-19):",
            *problems,
            "",
            "A bind mount is not covered by blanking a variable: `env_file: - .env` requires "
            "`.env` to sit beside the Compose file, so a mount of the project directory — or "
            "of anything above it — hands the container the superuser credential whatever the "
            "`environment:` block says. `db:5432` is reachable from every service on this "
            "network and accepts that role over scram, which makes it a working route to a "
            "role that bypasses every grant and every row-level security policy. If the mount "
            "is genuinely needed, add it to `ALLOWED_BIND_MOUNTS` under the file and service "
            "that declare it, in a reviewed diff, and say in the pull request what the "
            "container can now read.",
        ]
    )


def test_the_allowlist_permits_no_mount_the_compose_files_do_not_declare(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """`ALLOWED_BIND_MOUNTS` is an inventory of what exists, not a set of permissions.

    The other direction of the rule above, and it is what keeps the allowlist
    from growing. An entry nothing exercises is a permission nobody re-reads:
    the mount it was written for is deleted, the entry stays, and the next
    service to be given that name inherits a permission granted for a reason
    that no longer applies. That is `docs/MISTAKES.md` entry 1 in the shape a
    security control takes it.

    The mutation it must kill is an entry added speculatively — a fifth key, or
    a second source under an existing key — for a mount no Compose file makes.
    It also fails if a legitimate mount is *removed* from a Compose file without
    the entry going with it, which is the same fact from the other side and is
    the answer someone wants when they ask what the allowlist is for.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so every allowlist entry would look "
            "unused and this test would report the allowlist as speculative when the file is "
            "what went missing."
        )
    assert ALLOWED_BIND_MOUNTS, (
        "ALLOWED_BIND_MOUNTS is empty, so the rule above forbids every mount and this one "
        "checks nothing. An empty allowlist is a real possibility — it is what a stack with no "
        "bind mounts at all would have — but the two Compose files declare two today, so an "
        "empty one means the constant went rather than the mounts."
    )

    directories = {path.name: path.parent for path, _ in documents}
    mounted = declared_bind_mounts(documents)

    problems: list[str] = []
    for (file_name, service_name), allowed in sorted(ALLOWED_BIND_MOUNTS.items()):
        if file_name not in directories:
            problems.append(
                f"({file_name}, {service_name}) names a Compose file this suite does not read"
            )
            continue
        declared = mounted.get((file_name, service_name))
        if declared is None:
            problems.append(f"{file_name} declares no `{service_name}` service to mount anything")
            continue
        for entry in sorted(allowed):
            source = normalised_bind_source(entry, directories[file_name])
            if source not in declared.sources:
                problems.append(
                    f"{file_name}: `{service_name}` is permitted {entry} ({source}) and mounts "
                    f"{sorted(declared.sources) or 'nothing'}"
                )

    assert not problems, "\n".join(
        [
            "ALLOWED_BIND_MOUNTS permits a mount no Compose file declares:",
            *problems,
            "",
            "The allowlist enumerates what exists rather than what would be acceptable. A "
            "permission left behind by a deleted mount is granted to whatever is written under "
            "that name next, and nobody re-reads it — so an entry goes in the same change as "
            "the mount it describes and comes out in the same change as its removal.",
        ]
    )


def test_no_service_bind_mounts_a_sensitive_host_path(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """`SENSITIVE_BIND_SOURCES` still refuses by name, behind the allowlist.

    Kept rather than replaced, and E0-19's decision says why: a socket path that
    somehow enters the allowlist should still fail here. The mutation is an
    `ALLOWED_BIND_MOUNTS` entry naming `/var/run/docker.sock` — which makes the
    rule above pass and this one fail, and that combination is the whole point
    of keeping two checks over one resolved set.

    It is wider than the E0-03 rule it grew out of in one way worth naming: that
    one compared `worker` and `beat` against `api`, so the docker socket mounted
    into *every* application service, `api` included, satisfied it. This asks
    the question absolutely. The relative comparison stays where it is, because
    a privilege `api` legitimately gains later should not have to be granted
    twice.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so it declares no mounts and a search "
            "for a sensitive one reports it clean."
        )
    assert SENSITIVE_BIND_SOURCES, (
        "SENSITIVE_BIND_SOURCES is empty, so this rule forbids nothing and passes over any "
        "file at all. The list is the test's choice and is meant to grow, never to empty."
    )

    problems = sensitive_bind_mounts(documents)

    assert not problems, "\n".join(
        [
            "A service bind-mounts a host path whose contents are, in practice, the host:",
            *problems,
            "",
            "The docker socket is root on the host, /proc and /sys are the kernel, and /etc "
            "holds the shadow file. `worker` is the container E0-13 runs untrusted comment "
            "text through. This check sits behind the allowlist deliberately: if the mount "
            "reached the allowlist, the allowlist entry is the thing to argue about.",
        ]
    )


def test_no_compose_file_declares_a_volume_this_module_cannot_resolve(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """A volume shape the reader cannot classify is a red, never a silence.

    The same move as `ALLOWED_TOP_LEVEL_KEYS` one level down. The rules above
    are complete over the volume shapes this module reads and blind to any
    other, so a shape it cannot classify has to fail loudly — `external: true`
    puts the volume's definition somewhere this file cannot see, an `nfs`
    `device:` is a path on another machine, and a service naming a volume the
    top-level section does not declare cannot be resolved at all.

    The mutation this must kill is the tempting one: treating an unclassifiable
    `driver_opts` as "not a bind" and moving on, which is how a mount enters
    through the one shape nobody modelled. Read `named_volume_source` for what
    is refused and why.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so it declares no volumes and there "
            "is nothing here to fail to classify."
        )

    problems = unreadable_volume_declarations(documents)

    assert not problems, "\n".join(
        [
            "A Compose file declares a volume this module has not been taught to read:",
            *problems,
            "",
            "The mount rules above resolve a named volume through the top-level `volumes:` "
            "section and treat a bind-type `device:` as a host path. A shape they cannot "
            "classify is refused rather than passed over, because passing it over is how the "
            "docker socket arrives under a name nobody looks at. Teach this module the shape "
            "in the same change that adds it, and say here why the mount rules still hold.",
        ]
    )


def test_the_bind_reader_finds_the_mounts_the_compose_files_declare_today(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """A control: the reader finds the two real mounts, and it is not blind.

    **A red here means these tests are broken, not that the Compose files are.**
    Every rule in this section is phrased as "nothing is mounted that should not
    be", and every one of them passes over a reader that finds nothing at all —
    a normaliser that returns the empty string, a `volumes:` key read under the
    wrong name, a walk that stops at the first entry. `docs/MISTAKES.md`
    entry 35: require the reader to *find* what is certainly there.

    The expected paths are built with `pathlib` from the fixture, deliberately
    not by calling `normalised_bind_source` — an expectation computed by the
    thing under test agrees with it however wrong both are (entry 19).
    """
    assert base_compose and override_compose, (
        "One of the Compose files does not exist or declares nothing, so the reader has "
        "nothing to find and this control cannot tell a blind reader from an absent file."
    )

    root = base_compose_path.parent
    mounted = declared_bind_mounts(
        (
            (base_compose_path, base_compose),
            (override_compose_path, override_compose),
        )
    )

    initdb = mounted.get(
        (base_compose_path.name, CREDENTIAL_OWNING_SERVICE), BindMounts(frozenset(), ())
    )
    assert initdb.sources == {str(root / "scripts" / "db-init")}, (
        f"The reader says `{CREDENTIAL_OWNING_SERVICE}` mounts {sorted(initdb.sources)} from "
        f"{base_compose_path.name}. It mounts `./scripts/db-init` at "
        "/docker-entrypoint-initdb.d, which is where scripts/db-init creates the application "
        "and Care roles at initdb (ADR 0009), and a reader that cannot see that mount cannot "
        "see any of them."
    )

    reloaded = {
        name
        for (file_name, name), mounts in mounted.items()
        if file_name == override_compose_path.name and str(root / "backend") in mounts.sources
    }
    assert reloaded == {API_SERVICE, *JOB_SERVICES}, (
        f"The reader finds the development reload mount on {sorted(reloaded)} in "
        f"{override_compose_path.name}, and the override merges `x-development-source` into "
        f"{sorted({API_SERVICE, *JOB_SERVICES})}. The anchor is resolved by the YAML parser, so "
        "a reader that misses it is reading service bodies wrongly rather than reading a file "
        "that changed."
    )


def test_the_sample_documents_are_keyed_by_the_names_the_real_compose_files_use(
    base_compose_path: Path,
    override_compose_path: Path,
) -> None:
    """A control: the boundary tests below use the file names the allowlist is keyed by.

    **A red here means these tests are broken, not the Compose files.** Every
    refusal test below asserts that a mount is refused, and a sample keyed to a
    file name `ALLOWED_BIND_MOUNTS` does not know would be refused for the
    trivial reason that its allowlist is empty — including the samples that
    exist to prove a *legitimate* mount is allowed, which would then fail and
    say so. This is the half that would not: the near-miss and project-root
    tests would stay green through a rename with nothing checking them.
    """
    assert SAMPLE_BASE_PATH.name == base_compose_path.name, (
        f"The samples below are keyed to {SAMPLE_BASE_PATH.name} and the suite reads "
        f"{base_compose_path.name}. `ALLOWED_BIND_MOUNTS` is keyed by file name, so the two "
        "have to be the same name or the boundary tests are asserting against an empty "
        "allowlist."
    )
    assert SAMPLE_OVERRIDE_PATH.name == override_compose_path.name, (
        f"The samples below are keyed to {SAMPLE_OVERRIDE_PATH.name} and the suite reads "
        f"{override_compose_path.name}."
    )
    assert {name for name, _ in ALLOWED_BIND_MOUNTS} == {
        base_compose_path.name,
        override_compose_path.name,
    }, (
        "ALLOWED_BIND_MOUNTS is keyed by file names other than the two this suite reads: "
        f"{sorted({name for name, _ in ALLOWED_BIND_MOUNTS})}. An entry under a name nothing "
        "opens permits a mount in a file nothing checks."
    )


def test_mounting_the_project_directory_is_refused_and_the_message_names_the_env_file() -> None:
    """E0-19 criterion 1: the message says which mount, and why *that* directory.

    `- ./:/app/repo:ro` on `worker` is the exact edit the ticket names, and a
    refusal that says only "not in the allowlist" leaves its reader adding an
    allowlist entry. The project directory is not one host path among many: it
    is where `.env` is, because `env_file: - .env` resolves against it, so this
    mount undoes the blanking that ADR 0009's second bound is made of.

    The mutation this kills is a message that names neither — a rule that fails
    with a count, or with the service name alone. The near miss is a message
    that names the mount and stops there, which is why `.env` is asserted as
    well.
    """
    document = sample_document("worker", ["./:/app/repo:ro"])
    problems = unallowlisted_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert len(problems) == 1, (
        f"Mounting the project directory on `worker` produced {problems!r}. It is one mount and "
        "it is not in the allowlist, so it is exactly one problem."
    )
    message = problems[0]

    assert str(SAMPLE_PROJECT_DIRECTORY) in message, (
        f"The refusal does not name the mount: {message!r}. A reader who cannot see which path "
        "was refused cannot tell a deliberate mount from a typo."
    )
    assert "worker" in message, f"The refusal does not name the service: {message!r}."
    assert ".env" in message, (
        f"The refusal does not say that .env lives in the project directory: {message!r}. That "
        "sentence is the whole reason this mount is fatal rather than untidy — `env_file: - "
        ".env` resolves against this directory, so the mount hands over the superuser pair the "
        "`environment:` block blanked."
    )


@pytest.mark.parametrize(
    "spelling",
    [
        "./:/app/repo:ro",
        ".:/app/repo:ro",
        "/srv/pulse:/app/repo:ro",
        "//srv/pulse:/app/repo:ro",
        "/srv/pulse/./:/app/repo:ro",
        "/srv//pulse:/app/repo:ro",
        "../pulse:/app/repo:ro",
    ],
)
def test_an_unallowlisted_mount_is_refused_however_its_host_path_is_spelled(
    spelling: str,
) -> None:
    """E0-19 route 4: the comparison is over normalised paths, not over spellings.

    Measured against the local Docker daemon on 2026-08-21 by the orchestrating
    session — not by the author of this test, and recorded here as somebody
    else's measurement for that reason. A Compose file declared four spellings
    of one host directory: a relative source with a `.` segment, a source with
    doubled leading and internal separators, a relative source through `..`, and
    an absolute source with an internal doubled separator. In
    `docker compose config` the `.`-segment source came back collapsed and the
    `..` source resolved against the project directory, while the doubled
    separators survived verbatim. **All four mounted**, and the container read
    the host's marker file through every one.

    So the spellings are not equivalent to the daemon's *renderer* and are
    entirely equivalent to its *mounts*, and this module reads raw YAML rather
    than rendered output. Every one of these is `- ./:/app/repo:ro` written
    differently, and every one has to be refused the same way.

    The mutation this kills is a comparison against the source as spelled, which
    is what the E0-03 reader did — it only stripped a trailing slash. The near
    miss is a normaliser that handles the ordinary cases and leaves
    `//srv/pulse` alone, because `posixpath.normpath` preserves exactly two
    leading slashes; that spelling is in this list for that reason and has a
    test of its own below.
    """
    document = sample_document("worker", [spelling])

    problems = unallowlisted_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert problems, (
        f"`- {spelling}` on `worker` was not refused. It resolves to "
        f"{normalised_bind_source(spelling.split(':')[0], SAMPLE_PROJECT_DIRECTORY)!r}, which is "
        "the project directory — the directory `.env` lives in — and no service has it in its "
        "allowlist. A spelling nobody anticipated has to fail closed; that is the whole reason "
        "the rule is an allowlist over normalised sources."
    )


def test_the_development_reload_mount_is_allowed_in_the_override() -> None:
    """The legitimate mount passes where it is declared, which is half the rule.

    Without this half, `ALLOWED_BIND_MOUNTS` could be empty and every refusal
    test in this section would still pass — a rule that forbids everything is
    not a rule, it is a stop. The override mounts the checkout read-only over
    the copy the image installed, on all three application services, and ADR
    0011 is where that is argued.

    The mutation this kills is deleting the override's entries from the
    allowlist, or narrowing them to `api` — the reading someone reaches for when
    they see three entries that look duplicated.
    """
    document = sample_document(
        "worker",
        ["./backend:/app/backend:ro"],
        extra_services={
            "api": {"volumes": ["./backend:/app/backend:ro"]},
            "beat": {"volumes": ["./backend:/app/backend:ro"]},
        },
    )

    problems = unallowlisted_bind_mounts(one_compose_file(SAMPLE_OVERRIDE_PATH, document))

    assert not problems, "\n".join(
        [
            "The development reload mount was refused in the file that is allowed to declare it:",
            *problems,
            "",
            "`./backend` mounted read-only into `api`, `worker` and `beat` is what the "
            "development override is for (ADR 0011), and all three get it because an edit that "
            "reaches the API and not the worker leaves two containers running different code. "
            "If it is genuinely no longer wanted, the entries come out of ALLOWED_BIND_MOUNTS "
            "in the same change as the mount.",
        ]
    )


def test_the_development_reload_mount_is_refused_in_the_base_file() -> None:
    """The same mount in the base file is a different thing, and fails.

    The other direction of the pair above, and the reason `ALLOWED_BIND_MOUNTS`
    is keyed by file at all. `docker-compose.override.yml` is read on a laptop
    and in CI and by no deployment; `docker-compose.yml` is read by all of them.
    A source mount in the base file puts a writable-in-principle checkout into
    production containers and takes the installed wheel out of the import path —
    the packaging regression ADR 0011's base-file-only pass exists to catch,
    arriving as a Compose edit rather than as a Dockerfile one.

    The mutation this kills is an allowlist keyed by service name alone, which
    is the simplification anyone would try: it makes this document pass, and it
    is exactly the asymmetry the blanking rule above was broken by in reviewer
    pass 4.
    """
    document = sample_document("worker", ["./backend:/app/backend:ro"])

    problems = unallowlisted_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert problems, (
        "`- ./backend:/app/backend:ro` on `worker` in docker-compose.yml was not refused. That "
        "mount is allowed in docker-compose.override.yml, which no deployment reads, and it is "
        "a different thing in the file every deployment runs. If the allowlist has stopped "
        "being keyed by file, every development-only mount is now permitted in production."
    )


@pytest.mark.parametrize(
    ("path_name", "service_name", "spelling", "allowed"),
    [
        ("override", "api", "./backend2:/app/backend:ro", "./backend"),
        ("override", "api", "./backend/../backend2:/app/backend:ro", "./backend"),
        ("base", "db", "./scripts:/docker-entrypoint-initdb.d:ro", "./scripts/db-init"),
        ("base", "db", "./scripts/db-init2:/docker-entrypoint-initdb.d:ro", "./scripts/db-init"),
    ],
)
def test_a_mount_one_path_segment_from_an_allowed_source_is_refused(
    path_name: str,
    service_name: str,
    spelling: str,
    allowed: str,
) -> None:
    """The nearest passing case, which is the one a mutation battery has to include.

    `./scripts` is the parent of an allowed source and `./backend2` is a sibling
    of one; both are a single character away from a mount that passes, and both
    reach files no container is meant to read — `scripts/` holds `db-init` and
    `seed.py`, and a sibling directory is whatever somebody puts there next.

    The mutation this kills is a comparison by prefix or by `startswith`, which
    is the natural way to write "is this under something allowed" and which
    admits `./backend2` for `./backend` outright. The pair's other direction is
    the test above: the exactly-allowed source passes.
    """
    path = {"base": SAMPLE_BASE_PATH, "override": SAMPLE_OVERRIDE_PATH}[path_name]
    document = sample_document(service_name, [spelling])

    problems = unallowlisted_bind_mounts(one_compose_file(path, document))

    assert problems, (
        f"`- {spelling}` on `{service_name}` was not refused in {path.name}, where the allowlist "
        f"permits {allowed!r} and nothing else. It resolves to "
        f"{normalised_bind_source(spelling.split(':')[0], SAMPLE_PROJECT_DIRECTORY)!r}, which is "
        "not that path. A comparison that admits a neighbour of an allowed source is a prefix "
        "test wearing an allowlist's name."
    )


def test_a_service_with_no_allowlist_entry_may_not_mount_an_allowed_source() -> None:
    """The allowlist is keyed by service as well as by file, and this is that half.

    `./scripts/db-init` is permitted — to `db`, in the base file, because that
    is the directory Postgres runs at `initdb` to create the application and
    Care roles. Mounted into `redis`, or into `worker`, it is a container
    reading the SQL and shell that provision the cluster.

    The mutation this kills is a rule that flattens the allowlist to a set of
    sources and asks only whether the path appears in it. That version passes
    this document, and it turns every legitimate mount into a permission the
    whole stack holds.
    """
    document = sample_document("redis", ["./scripts/db-init:/docker-entrypoint-initdb.d:ro"])

    problems = unallowlisted_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert problems, (
        "`- ./scripts/db-init:...` on `redis` was not refused. That source is allowed to `db` "
        "and to nothing else: the allowlist is keyed by (file, service), and a rule that reads "
        "only the sources grants every service what any one of them may mount."
    )


def test_a_bind_source_built_from_an_interpolation_is_refused() -> None:
    """A source this module cannot evaluate is refused by one rule or the other.

    `- ${HOST_TOOLS}:/tools:ro` names a path that depends on the environment
    Compose was run with, and no static reading of the file can say what it is —
    or even whether it is a path at all rather than a volume name, since neither
    shape can be told from the other before expansion.

    **Which rule catches it is not the property under test**, so both refusal
    channels are read: a source that looks like a volume name lands in the
    unreadable-declaration rule and one that looks like a path lands in the
    allowlist. What matters is that a spelling this module cannot evaluate
    produces a red rather than a silence, and asserting only the channel that
    happens to fire today would make a later, equally correct classification
    look like a regression.

    The mutation this kills is an implementation that expands interpolations
    against `.env.example`, or against `os.environ`, and then compares: the
    first makes the answer depend on a documentation file, the second on the
    machine running the tests, and both can resolve to an allowed path while the
    deployment mounts something else entirely.
    """
    document = sample_document("worker", ["${HOST_TOOLS}:/tools:ro"])

    documents = one_compose_file(SAMPLE_BASE_PATH, document)
    problems = unallowlisted_bind_mounts(documents) + unreadable_volume_declarations(documents)

    assert problems, (
        "`- ${HOST_TOOLS}:/tools:ro` on `worker` was refused by neither rule. What it mounts "
        "depends on the environment Compose reads, so it cannot be checked here and must not "
        "be assumed harmless."
    )


@pytest.mark.parametrize(
    "spelling",
    [
        "/var/run/docker.sock",
        "/var/run/./docker.sock",
        "//var/run/docker.sock",
        "/var//run/docker.sock",
        "/var/run/../run/docker.sock",
    ],
)
def test_a_sensitive_host_path_is_refused_however_it_is_spelled(spelling: str) -> None:
    """The denylist behind the allowlist reads the same normalised set. E0-19 route 4.

    `/var/run/./docker.sock` and `//var/run/docker.sock` both survive verbatim
    into `docker compose config`, so the E0-03 comparison — a set membership
    test against the source as spelled — missed both while the socket mounted
    exactly as it always does. The daemon measurement recorded on the allowlist
    test above covers the reachability half of this.

    The mutation this kills is normalising the read sources and not
    `SENSITIVE_BIND_SOURCES`, or the reverse: a comparison is only as good as
    the agreement of its two sides, and either half alone passes every spelling
    in this list.
    """
    document = sample_document("worker", [f"{spelling}:/var/run/docker.sock"])

    problems = sensitive_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert problems, (
        f"`- {spelling}:...` on `worker` did not fail the sensitive check. It resolves to "
        f"{normalised_bind_source(spelling, SAMPLE_PROJECT_DIRECTORY)!r}, which is the docker "
        "socket — root on the host, for the container E0-13 runs untrusted comment text "
        "through."
    )


def test_a_named_volume_carrying_a_bind_device_fails_the_allowlist() -> None:
    """E0-19 route 2: a `driver_opts` bind is a bind, under the allowlist too.

    The service entry says `- host-root:/host`, which reads as a Docker volume
    and is a mount of `/` with a name in front of it. Any `device:` works, the
    project directory included, which is why this is a second spelling of route
    1 rather than a hazard of its own.

    The mutation this kills is a reader that treats a source without a leading
    `/`, `.` or `~` as a named volume and stops there — which is what the E0-03
    reader did, and its docstring said a named volume "contributes nothing".
    """
    document = sample_document(
        "worker",
        ["host-root:/host"],
        top_level={"host-root": {"driver_opts": {"type": "none", "device": "/", "o": "bind"}}},
    )

    problems = unallowlisted_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert problems, (
        "A named volume whose driver_opts bind `/` was not refused by the allowlist. The "
        "service entry names a volume rather than a path, so a reader that looks only at the "
        "entry sees a Docker volume — and the container gets the host's root filesystem, `.env` "
        "and all."
    )
    assert any(".env" in problem for problem in problems), (
        f"The refusal does not say that .env is inside what was mounted: {problems!r}. `/` is an "
        "ancestor of the project directory, so this mount carries the same consequence as "
        "mounting the project directory itself and the message has to say so."
    )


def test_a_named_volume_carrying_a_bind_device_fails_the_sensitive_check() -> None:
    """The same declaration, against the check that names the socket. E0-19 criterion 2.

    "Fails the same tests that catch it as a direct bind" is two tests — this
    one and the allowlist above it — and the note below this test says why it is
    not three any more. The mutation is the same one: a named volume resolved by
    the allowlist rule and not by the sensitive one, which is what happens if the
    resolution is done inside the allowlist's own function instead of in the
    reader both share.
    """
    document = sample_document(
        "worker",
        ["host-socket:/var/run/docker.sock"],
        top_level={
            "host-socket": {"driver_opts": {"type": "none", "device": "/var/run/docker.sock"}}
        },
    )

    problems = sensitive_bind_mounts(one_compose_file(SAMPLE_BASE_PATH, document))

    assert problems, (
        "The docker socket declared as a named volume with a bind `driver_opts` did not fail "
        "the sensitive check. It is the identical mount to `- /var/run/docker.sock:...`, which "
        "does fail it, and the difference is only where the path is written."
    )


# A third test used to sit here: the same named volume put through the
# privilege comparison, because "fails the same tests that catch it as a direct
# bind" was three tests while that rule read bind mounts. E0-19's security
# review made the privilege rule absolute over `PRIVILEGE_KEYS` alone (see
# `test_no_service_is_granted_a_privilege_its_image_does_not_carry`), so the
# tests that catch a direct bind are now the two above — the allowlist and the
# sensitive check — and both catch this shape. The criterion is met by those
# two; a third test asserting a rule that no longer reads mounts would have
# asserted nothing and stayed green forever.


def test_an_ordinary_named_volume_is_not_a_bind_source() -> None:
    """The other direction: `beat-schedule` and `postgres-data` are not host paths.

    A rule that called every named volume a bind would fail the base file on the
    two volumes it legitimately declares, and the fix somebody would reach for
    is an allowlist entry — which is a permission granted for a mount that does
    not exist. A local volume with no `driver_opts` names no host path, and
    saying so is not the same as failing to look.

    The mutation this kills is a resolver that returns the volume's *name* as a
    source when it cannot find a device, which is the shape a `dict.get` with a
    fallback takes.
    """
    document = sample_document(
        "beat",
        ["beat-schedule:/var/lib/celery"],
        top_level={"beat-schedule": None, "postgres-data": None},
    )

    documents = one_compose_file(SAMPLE_BASE_PATH, document)
    mounts = declared_bind_mounts(documents)[(SAMPLE_BASE_PATH.name, "beat")]

    assert mounts.sources == frozenset(), (
        f"An ordinary named volume resolved to {sorted(mounts.sources)}. `beat-schedule` is a "
        "Docker volume: it survives `docker compose restart beat` and it is not a piece of the "
        "host filesystem."
    )
    assert mounts.unreadable == (), (
        f"An ordinary named volume was refused as unreadable: {list(mounts.unreadable)}. A "
        "local volume with no driver_opts is the ordinary case, and refusing it would fail the "
        "base file on `postgres-data` and `beat-schedule` both."
    )


@pytest.mark.parametrize(
    ("shape", "volumes"),
    [
        ("a volume the top-level section does not declare", {}),
        ("an external volume", {"host-data": {"external": True}}),
        (
            "an nfs device",
            {
                "host-data": {
                    "driver_opts": {"type": "nfs", "device": ":/export", "o": "addr=10.0.0.1"}
                }
            },
        ),
        ("driver_opts with no device", {"host-data": {"driver_opts": {"type": "none"}}}),
    ],
)
def test_a_volume_declaration_this_module_cannot_classify_is_refused(
    shape: str,
    volumes: dict[str, Any],
) -> None:
    """Fail closed: an unclassifiable shape is a refusal, not a "not a bind".

    Each of these could be a host path and none of them can be read as one here.
    An external volume is defined outside this file; an `nfs` device is a path
    somewhere else; `driver_opts` with no `device:` is a shape this module has
    not been taught. The closed-set strategy the credential rules already use
    says the same thing about all four: refuse, and be taught in the change that
    needs it.

    The mutation this kills is the fallback branch — returning "no source" for
    anything the classifier does not recognise — which makes every one of these
    pass the allowlist silently. That is precisely how `include:` and top-level
    `secrets:` got past the credential rules in two earlier reviewer passes.
    """
    document = sample_document("worker", ["host-data:/data"], top_level=volumes)

    refusals = unreadable_volume_declarations(one_compose_file(SAMPLE_BASE_PATH, document))

    assert refusals, (
        f"{shape} was not refused. This module cannot say what it mounts, and a shape it cannot "
        "read has to fail loudly — a silent 'not a bind' is how the docker socket arrives under "
        "a name nobody looks at."
    )
    assert all("host-data" in refusal for refusal in refusals), (
        f"A refusal for {shape} does not name the volume it is about: {refusals!r}. The service "
        "name is in every one of these messages by construction, so naming the volume is what "
        "tells a reader which declaration to go and look at."
    )


@pytest.mark.parametrize(
    ("spelling", "canonical"),
    [
        ("./scripts/db-init", "/srv/pulse/scripts/db-init"),
        ("scripts/db-init", "/srv/pulse/scripts/db-init"),
        ("./scripts/./db-init", "/srv/pulse/scripts/db-init"),
        ("./scripts//db-init", "/srv/pulse/scripts/db-init"),
        ("/srv/pulse/scripts//db-init", "/srv/pulse/scripts/db-init"),
        ("//srv/pulse/scripts/db-init", "/srv/pulse/scripts/db-init"),
        ("../pulse/scripts/db-init", "/srv/pulse/scripts/db-init"),
        ("./scripts/db-init/", "/srv/pulse/scripts/db-init"),
        ("/var/run/./docker.sock", "/var/run/docker.sock"),
    ],
)
def test_an_alternate_spelling_normalises_to_the_canonical_host_path(
    spelling: str,
    canonical: str,
) -> None:
    """One host path, one string, whichever way the Compose file spells it.

    The five spellings the ticket names are all here — a `.` segment, a doubled
    internal separator, a leading `//`, a plain relative source, and a relative
    source through `..` — plus the trailing slash the E0-03 reader handled and
    the bare relative source that has no `./` in front of it. A relative source
    resolves against the **project directory**, which was measured during
    E0-03's review to be what Compose does regardless of the service's
    `working_dir`.

    The mutation this kills is each of the collapsing steps in turn. The near
    miss lives in the test below it: two paths that are genuinely different must
    stay different, so "return the project directory for everything" does not
    pass.
    """
    assert normalised_bind_source(spelling, SAMPLE_PROJECT_DIRECTORY) == canonical, (
        f"{spelling!r} normalised to "
        f"{normalised_bind_source(spelling, SAMPLE_PROJECT_DIRECTORY)!r} rather than to "
        f"{canonical!r}. Both spellings mount the same host directory — measured against the "
        "daemon on 2026-08-21 — so a comparison that tells them apart clears a mount that "
        "reaches the host."
    )


def test_a_leading_double_slash_is_collapsed_although_posixpath_preserves_it() -> None:
    """The one case `posixpath.normpath` will not do, asserted against `normpath` itself.

    POSIX leaves the meaning of a path beginning with exactly two slashes
    implementation-defined, so `normpath` keeps them — and collapses three or
    more. `//var/run/docker.sock` therefore survives a naive normalisation and
    compares unequal to `/var/run/docker.sock`, while mounting exactly the same
    socket; the orchestrator's 2026-08-21 daemon measurement covers the mounting
    half.

    Both halves are asserted here on purpose. The first says the helper
    collapses it. The second says `normpath` alone does not — which is what
    makes the first assertion evidence rather than a restatement of the
    implementation, and which will fail loudly if a future Python changes the
    rule out from under this comment.
    """
    assert normalised_bind_source("//var/run/docker.sock", SAMPLE_PROJECT_DIRECTORY) == (
        "/var/run/docker.sock"
    ), (
        "A leading `//` was not collapsed. `posixpath.normpath` preserves exactly two leading "
        "slashes, so this has to be done explicitly; without it the docker socket has a "
        "spelling that mounts and does not match."
    )
    assert posixpath.normpath("//var/run/docker.sock") == "//var/run/docker.sock", (
        "posixpath.normpath has stopped preserving two leading slashes. That is the premise "
        "this collapsing step exists for; if it is no longer true, read the change before "
        "deleting the step — the step is still correct, and this assertion is what says why it "
        "is there."
    )


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("./backend", "./backend2"),
        ("./scripts/db-init", "./scripts"),
        ("/var/run/docker.sock", "/var/run/docker.sock.bak"),
        ("../secret", "./secret"),
        ("./backend", "/backend"),
    ],
)
def test_two_different_host_paths_do_not_normalise_together(one: str, other: str) -> None:
    """The other direction of normalisation: it collapses spellings, never paths.

    A normaliser that returned a constant, or that truncated to the project
    directory, would pass every equality test above and make the allowlist
    permit everything under one entry. `../secret` and `./secret` are the pair
    worth reading twice: one leaves the project directory and the other does
    not, and a `..` handled by deletion rather than by resolution makes them the
    same string.
    """
    assert normalised_bind_source(one, SAMPLE_PROJECT_DIRECTORY) != normalised_bind_source(
        other, SAMPLE_PROJECT_DIRECTORY
    ), (
        f"{one!r} and {other!r} both normalised to "
        f"{normalised_bind_source(one, SAMPLE_PROJECT_DIRECTORY)!r}. They are different host "
        "paths, and an allowlist compared over a normaliser that conflates them permits the "
        "one it was not given."
    )


def test_the_normaliser_reads_nothing_from_the_filesystem(tmp_path: Path) -> None:
    """Textual, deliberately: no symlink resolution, no existence check.

    `Path.resolve()` is the obvious implementation and it makes the answer
    depend on what happens to exist on the machine running the tests, which is
    not a property of the Compose file at all. A developer with a symlinked
    checkout would get a different verdict from CI, and a source naming a path
    that does not exist yet — which is most of them, since the allowlist is
    compared before anything is created — would resolve to something else again.

    The mutation this kills is exactly that: `Path(...).resolve()` in place of
    the textual collapse. The symlink half fails under it immediately; the
    missing-directory half is the near miss, since `resolve(strict=False)`
    tolerates a path that is not there.
    """
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)

    assert normalised_bind_source("./link", tmp_path) == str(link), (
        "The normaliser followed a symlink. What a Compose file says it mounts is the path it "
        "wrote, and resolving it makes this suite's answer depend on the checkout it runs in."
    )

    missing = tmp_path / "nowhere"
    assert normalised_bind_source("./backend", missing) == f"{missing}/backend", (
        "The normaliser did not handle a project directory that does not exist. It is compared "
        "against paths nothing has created yet, so it cannot depend on the filesystem."
    )


@pytest.mark.parametrize("sample", BIND_CURRENCY_SAMPLES, ids=lambda sample: sample.currency)
def test_the_bind_reader_finds_a_mount_in_every_currency_it_claims(
    sample: BindCurrencySample,
) -> None:
    """A control: each way of declaring a host mount is found, one at a time.

    **A red here means these tests are broken, not the Compose files.** Every
    rule in this section reports absence, and absence is what a reader that
    cannot see a currency reports too — `docs/MISTAKES.md` entry 35, whose
    sharper half is that the currency a design deliberately uses is the one a
    guard is most likely to miss. Here that is the named volume: it is the
    spelling that looks like a Docker volume and mounts the host.

    Each sample is written so that only its own mechanism can catch it — the
    `type: none` volume carries an `o:` with no `bind` in it, and the `o: bind`
    volume declares no `type:` — so deleting either half of the classifier turns
    exactly one of these red while the refusal rules stay green.

    The whole path is exercised, from `bind_mounts_of` down, rather than the
    classifier alone: a resolution step that stops being called is the defect
    this is guarding, and a control that calls it directly cannot see that.
    """
    document = sample_document("worker", [sample.entry], top_level=sample.volumes)

    documents = one_compose_file(SAMPLE_BASE_PATH, document)
    mounts = declared_bind_mounts(documents)[(SAMPLE_BASE_PATH.name, "worker")]

    assert mounts.unreadable == (), (
        f"The reader refused the {sample.currency} sample as unclassifiable: "
        f"{list(mounts.unreadable)}. It is a shape this module claims to read."
    )
    assert mounts.sources == frozenset({sample.expected}), (
        f"The reader resolved the {sample.currency} sample to {sorted(mounts.sources)} rather "
        f"than to {[sample.expected]}. A currency the reader cannot see makes every rule above "
        "report a clean file over a mount it never looked at."
    )


def test_the_currency_samples_cover_every_currency_in_the_inventory() -> None:
    """A control over the control: the sample table matches the written-down inventory.

    **A red here means these tests are broken, not the Compose files.** The
    control above is parametrised over `BIND_CURRENCY_SAMPLES`, so deleting a
    sample deletes its own case and the remaining ones pass at the smaller size
    — four tests where there were six, with a currency going unread and nothing
    saying so. That is the failure E0-34's review found one level above this
    entry's rule, and the repair is an inventory the sample table cannot shrink:
    `BIND_DECLARATION_CURRENCIES` is written separately and compared here.
    """
    covered = [sample.currency for sample in BIND_CURRENCY_SAMPLES]

    assert sorted(covered) == sorted(BIND_DECLARATION_CURRENCIES), (
        f"The samples cover {sorted(covered)} and the inventory names "
        f"{sorted(BIND_DECLARATION_CURRENCIES)}. A currency in the inventory with no sample is "
        "a mechanism nothing proves the reader can see; a sample with no inventory entry is a "
        "mechanism nothing would notice the deletion of."
    )
    assert len(covered) == len(set(covered)), (
        f"Two samples claim the same currency: {covered}. A duplicate makes the comparison "
        "above pass with a currency missing."
    )


# ---------------------------------------------------------------------------
# What E0-19's own security review found, and what it moved.
#
# Five findings, every one of them established by running the attack against the
# guards above rather than by reading them, and every one green against the full
# suite when it was found. Three are the same shape as the four routes E0-19
# started from — a spelling just outside a rule that was phrased over the
# spellings somebody thought of — which is the shape this module's docstring
# says the closed-set strategy exists to stop, arriving one level in from where
# the strategy had been applied.
#
#   - A service key nothing read: `volumes_from: - db` grants `worker` every
#     mount `db` has, which is the whole Postgres data directory.
#   - A volume key read as inert: `name:` attaches the entry to a pre-created
#     host volume, and one `docker volume create --opt device=/` makes it the
#     host root.
#   - A privilege comparison defeated by the anchor it was written beside.
#   - A credential typed out as a literal in `command:`, which every
#     reference-following rule in this module passes.
#
# The fourth of those reversed a decision recorded in this module rather than
# extending it, and the reversal is written where the decision was.
# ---------------------------------------------------------------------------


def test_no_service_declares_a_key_this_module_cannot_read(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """The closed set of service keys, which is `ALLOWED_TOP_LEVEL_KEYS` one level in.

    The top-level rule bounds which *sections* a Compose file may declare and
    says nothing about what a service body may carry, so every rule in this
    module reads the parts of a service somebody thought to read.
    `volumes_from: - db` is the measurement E0-19's review made: it gives
    `worker` every mount `db` has — `/var/lib/postgresql/data`, the whole
    cluster on disk — and it passed the entire suite, because the mount rules
    read `volumes:` and `volumes_from` is not a volume.

    The mutation this must kill is that line, added to `worker` in
    `docker-compose.yml`. Four more were measured going past just as quietly and
    each is a case in the refusal test below: `cgroup: host`, `uts: host`,
    `runtime`, and `develop`. Enumerating them would have been a fourth round of
    the mistake this module's docstring records; what closes the set is refusing
    the sixth one nobody has thought of.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse declares no "
            "services, and a rule about the keys a service declares reports it clean."
        )

    problems = [
        problem
        for path, document in documents
        for problem in unreadable_service_keys(path, document)
    ]

    assert not problems, "\n".join(
        [
            "A service declares a key this module has not been taught to read:",
            *problems,
            "",
            f"Allowed today: {sorted(ALLOWED_SERVICE_KEYS)}. This is not a style rule. Every "
            "rule in this module reads a service body through a key it knows the name of, so a "
            "key outside this set is configuration nothing here inspects — `volumes_from:` "
            "grants every mount another service has, `cgroup:` and `uts:` and `runtime:` each "
            "change what the container is isolated by. Teach this module the key in the same "
            "change that adds it, say here why the rules above still hold over it, and then "
            "add it to the list.",
        ]
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("volumes_from", ["db"]),
        ("cgroup", "host"),
        ("uts", "host"),
        ("runtime", "sysbox-runc"),
        ("develop", {"watch": [{"action": "sync", "path": ".", "target": "/app"}]}),
    ],
)
def test_a_service_key_outside_the_closed_set_is_refused(key: str, value: Any) -> None:
    """Each of the five the reviewer ran past the guards, refused by name.

    `volumes_from: - db` is the sharp one and the rest are the argument for a
    closed set rather than five denials: `cgroup: host` puts the container in
    the host's cgroup namespace, `uts: host` gives it the host's hostname
    namespace, `runtime:` replaces the runtime that enforces any of it, and
    `develop.watch` syncs a host directory into the container by a route that
    is not `volumes:` at all. Not one of them is read by any rule in this
    module, and every one of them passed the whole suite.

    The mutation this kills is the removal of any single refusal — which,
    because the rule is a closed set rather than a list of denials, is the
    removal of the rule itself. The near miss is the key that *is* allowed:
    `volumes:` on the same service is read, resolved and checked, and the test
    above passes the real files that use it.
    """
    document = {"services": {"worker": {key: value}}}

    problems = unreadable_service_keys(SAMPLE_BASE_PATH, document)

    assert problems, (
        f"`{key}:` on `worker` was not refused. Nothing in this module reads it, so whatever it "
        "grants is granted invisibly — which is the whole reason the set of service keys is "
        "closed rather than enumerated."
    )
    assert all(key in problem and "worker" in problem for problem in problems), (
        f"The refusal does not name the key and the service: {problems!r}. A reader who cannot "
        "see which line to look at cannot tell a deliberate addition from a paste."
    )


def test_the_service_key_reader_finds_the_keys_the_compose_files_declare(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """A control: the reader sees service keys, anchor-merged ones included.

    **A red here means these tests are broken, not the Compose files.** The rule
    above reports absence, and a reader that finds no keys at all reports the
    same absence. `docs/MISTAKES.md` entry 35: require it to find each thing on
    a subject that certainly has it.

    The anchor half is the one that matters. `api` writes `environment:` and
    `depends_on:` in its own block and gets `build`, `env_file` and
    `environment` from `x-application`; PyYAML resolves the merge before any
    rule here looks, so those three are service keys by the time this reads
    them. A reader built from the lines visible in the file would report a
    smaller set and the refusal rule would be blind to anything added to the
    anchor — which is precisely where two earlier findings put their payload.
    """
    assert base_compose, f"{base_compose_path} does not exist or declares nothing."

    keys = service_keys_of(base_compose)
    assert keys, "The reader found no services at all in the base Compose file."

    empty = sorted(name for name, declared in keys.items() if not declared)
    assert not empty, (
        f"The reader says {empty} declare no keys at all. Every service in this file declares "
        "at least an image or a build, so a service with an empty key set is a reader that "
        "cannot see a service body rather than a service that is empty."
    )

    merged = {"build", "env_file", "environment"}
    assert merged <= set(keys.get(API_SERVICE, ())), (
        f"The reader says `{API_SERVICE}` declares {sorted(keys.get(API_SERVICE, ()))}, which "
        f"does not include all of {sorted(merged)}. Those three come from the `x-application` "
        "anchor rather than from `api`'s own block, and a reader that misses them is reading "
        "the file rather than the parsed document — which leaves everything the anchor carries "
        "outside every rule in this module."
    )

    assert {"image", "volumes", "healthcheck"} <= set(keys.get(CREDENTIAL_OWNING_SERVICE, ())), (
        f"The reader says `{CREDENTIAL_OWNING_SERVICE}` declares "
        f"{sorted(keys.get(CREDENTIAL_OWNING_SERVICE, ()))}. It runs a pinned image, mounts two "
        "volumes and declares a health check, so a reader that sees fewer than three kinds of "
        "key here is not reading service bodies."
    )


def test_the_closed_service_key_set_holds_no_key_the_compose_files_do_not_use(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """The other direction: the set enumerates what exists, not what would be fine.

    The same rule as `ALLOWED_BIND_MOUNTS` holding no unused entry, and it is
    what keeps a closed set closed. An entry admitted for a key nothing declares
    is a key nobody has had to think about — which is exactly the sentence the
    `networks` entry earned when it was taken off `ALLOWED_TOP_LEVEL_KEYS`.

    The mutation this kills is an entry added on the way past: `volumes_from` or
    `privileged` written into `ALLOWED_SERVICE_KEYS` to make a red go away.
    """
    for path, document in (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    ):
        assert document, (
            f"{path} does not exist or declares nothing, so every entry would look unused and "
            "this test would report the constant as speculative when a file is what went."
        )

    declared = {
        key
        for document in (base_compose, override_compose)
        for keys in service_keys_of(document).values()
        for key in keys
    }
    unused = sorted(key for key in ALLOWED_SERVICE_KEYS if key not in declared)

    assert not unused, "\n".join(
        [
            f"ALLOWED_SERVICE_KEYS admits keys no service declares: {unused}.",
            "",
            "A closed set that admits a feature the repository does not use is not closed; it "
            "is a smaller open one. The entry comes back in the change that first needs it, "
            "with a sentence saying why the rules in this module still hold over it.",
        ]
    )


@pytest.mark.parametrize(
    ("shape", "body"),
    [
        ("a pre-created volume named directly", {"name": "pre-created-host-root"}),
        ("a driver this file does not describe", {"driver": "foo"}),
        (
            "a pre-created volume with driver_opts beside it",
            {
                "name": "pre-created-host-root",
                "driver_opts": {"type": "none", "device": "/var/lib/probe"},
            },
        ),
    ],
)
def test_a_named_volume_defined_outside_this_file_is_refused(
    shape: str, body: dict[str, Any]
) -> None:
    """`name:` and `driver:` are `external:` under other spellings. E0-19's review.

    Both were on `READABLE_VOLUME_KEYS` and both resolved to "not a bind, not a
    refusal", which is the worst of the three answers a closed set can give.
    A `name:` attaches the volume to a **pre-created** Docker volume under
    exactly that name — no project prefix, so it is not namespaced to this stack
    — and

        docker volume create --opt type=none --opt device=/ --opt o=bind pre-created-host-root

    run once beforehand makes the innocuous-looking entry a mount of the host
    root, with nothing in the Compose file saying so. A `driver:` hands the
    decision to a plugin. The reason `external: true` is refused is true of both
    word for word: the thing being mounted is defined somewhere this file cannot
    see, and no amount of reading this file will say what it is.

    The mutation this kills is re-admitting either key to
    `READABLE_VOLUME_KEYS`. The third case is the near miss: a `name:` beside a
    `driver_opts` that *is* readable must still be refused, because the `name:`
    is what decides which volume is attached and the `driver_opts` is then only
    what would be used if it had to be created.
    """
    document = sample_document("worker", ["host-root:/host"], top_level={"host-root": body})

    refusals = unreadable_volume_declarations(one_compose_file(SAMPLE_BASE_PATH, document))

    assert refusals, (
        f"{shape} was not refused. What that volume mounts is decided outside this file, so "
        "reading it as an ordinary Docker volume is reading an assumption rather than the "
        "configuration."
    )
    assert all(
        "host-root" in refusal for refusal in refusals
    ), f"A refusal for {shape} does not name the volume: {refusals!r}."


def test_a_privilege_granted_through_the_shared_anchor_is_refused() -> None:
    """The measurement that reversed the relative rule, written as a test.

    One line on `x-development-source` in the override reaches `api`, `worker`
    and `beat`, because all three merge it — so the parsed document has
    `privileged: true` on all three, which is the shape below. The rule this
    replaced asked whether `worker` held more than `api` and the answer was no:
    they held the same thing, and the thing was the host.

    Every service is named in the failure, not just the two job services, and
    that is the reversal in one assertion: under the old rule `api` was the
    baseline and could not fail at all.

    The mutation this kills is a return to the comparison — any rule phrased as
    a difference between two services passes this document.
    """
    granted = {"privileged": True}
    document = {
        "services": {
            "api": dict(granted),
            "worker": dict(granted),
            "beat": dict(granted),
        }
    }

    problems = privilege_grants(SAMPLE_OVERRIDE_PATH, document)

    named = {name for name in ("api", "worker", "beat") if any(name in p for p in problems)}
    assert named == {"api", "worker", "beat"}, (
        f"A privilege written on the shared anchor was reported for {sorted(named)} rather than "
        "for all three services that merge it. `api` is not a baseline: the anchor grants it "
        "the same thing, which is how the comparison this rule replaced was defeated with the "
        "whole suite green."
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("privileged", True),
        ("pid", "host"),
        ("network_mode", "host"),
        ("userns_mode", "host"),
        ("cap_add", ["SYS_ADMIN"]),
        ("devices", ["/dev/kmsg:/dev/kmsg"]),
        ("user", "root"),
    ],
)
def test_each_privilege_key_is_refused_on_its_own(key: str, value: Any) -> None:
    """Every key on the list, one at a time, so a deletion from it turns one test red.

    Six of these seven were run past the guards in E0-19's review, one per run,
    each granting the three application services something of the host and each
    green against the whole suite. `user: root` is the seventh and is the oldest
    of them: the API image fixes a non-root user and a service-level `user:`
    overrides it, which E0-02 checks on the running container and nothing
    checked in the file.

    Parametrised one key per case rather than all seven in one document,
    deliberately: a single document containing all of them stays red when six of
    the seven stop being read, and the failure would name the rule rather than
    the key.
    """
    document = {"services": {"worker": {key: value}}}

    problems = privilege_grants(SAMPLE_BASE_PATH, document)

    assert problems, (
        f"`{key}: {value!r}` on `worker` was not reported as a grant. It is on PRIVILEGE_KEYS "
        "because it hands the container something the image does not carry, and nothing "
        "dynamic notices: the stack comes up healthy either way."
    )
    assert all(
        key in problem for problem in problems
    ), f"The report does not name the key: {problems!r}."


def test_a_privilege_key_that_declares_nothing_is_not_a_grant() -> None:
    """The other direction: `privileged: false` and an empty `cap_add` grant nothing.

    A rule that reported every appearance of a key on the list would fail a file
    that says `privileged: false` — which is a statement that the container is
    *not* privileged — and the repair someone reaches for is to weaken the rule
    rather than to read the value. `privilege_declarations` drops falsy values
    for that reason, and this is the assertion that says so through the whole
    path.
    """
    document = {
        "services": {
            "worker": {"privileged": False, "cap_add": [], "security_opt": None},
        }
    }

    problems = privilege_grants(SAMPLE_BASE_PATH, document)

    assert not problems, "\n".join(
        [
            "A privilege key that grants nothing was reported as a grant:",
            *problems,
            "",
            "`privileged: false` is the absence of the privilege written down. Reporting it "
            "makes the rule fail on a file being explicit, and the fix that follows is a "
            "weaker rule.",
        ]
    )


def superuser_literals(documented: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """The two credential values, labelled, as `.env.example` writes them.

    Taken from the file rather than written down here, because CI does
    `cp .env.example .env` and starts the stack from it: the placeholder in that
    file *is* the value in the pipeline, so it is the string that must not be
    typed into a Compose file.
    """
    return tuple(
        (f"the superuser {label} ({variable})", documented.get(variable, ""))
        for variable, label in (
            ("DB_SUPERUSER", "role name"),
            ("DB_SUPERUSER_PASSWORD", "password"),
        )
    )


def test_no_service_writes_the_superuser_credential_into_a_string(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
    documented_env: dict[str, str],
) -> None:
    """The credential typed out, anywhere in a service body. E0-19's security review.

    Every credential rule above this one follows `${...}` references, so each of
    them sees `${DB_SUPERUSER}` wherever it is written and none of them sees
    anything at all when the value is typed out instead. The review measured it:
    the superuser URL spelled into `worker`'s `command:`, suite green. There is
    no `environment:` entry to read, no interpolation to resolve, and the
    container gets a working superuser connection from its own command line.

    The mutation this must kill is that line — a `command:` entry containing
    `postgresql://pulse_admin:replace-me-admin@db:5432/pulse`. The same string
    in `entrypoint:`, in `healthcheck.test`, in a label or in `build.args`
    reaches a container too, and the walk is recursive rather than a list of
    those five keys for the reason this module keeps relearning: a list of keys
    is a list of the ones somebody thought of.

    **Every service, `db` included.** `db`'s exemption is from *reading* the
    credential by interpolation, which is how a deployment's real `.env` reaches
    Postgres. A literal is the `.env.example` placeholder committed into a
    Compose file, which is a credential in the repository wherever it sits.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so it declares no strings and a search "
            "through them reports it clean."
        )

    credentials = superuser_literals(documented_env)
    for label, value in credentials:
        assert value, (
            f".env.example does not document {label}, so this rule has nothing to search for "
            "and would report every file clean."
        )
        assert "${" not in value, (
            f"{label} is documented as {value!r}, which is itself an interpolation. This rule "
            "compares against the value as written; if `.env.example` starts assembling the "
            "superuser credential from other entries, it needs the resolved value instead — "
            "which is what `test_env_example_resolves.py` reads."
        )

    problems = [
        problem
        for path, document in documents
        for problem in credential_literals(path, document, credentials)
    ]

    assert not problems, "\n".join(
        [
            "A Compose file writes the superuser credential out as a literal (ADR 0009):",
            *problems,
            "",
            "No `${...}` is involved, so every rule above this one passes it: they follow "
            "references, and there is no reference here. The container holds the credential "
            "the moment the string reaches it, and `db:5432` is reachable from every service "
            "on this network over scram. Interpolate the variable instead — and if the value "
            "genuinely belongs in the repository, it is not a credential and `.env.example` "
            "should stop calling it one.",
        ]
    )


def test_a_credential_literal_in_a_service_command_is_caught() -> None:
    """The reviewer's measured case: the URL typed into `worker`'s `command:`.

    Nothing in the line interpolates anything, so the transitive walkers see no
    variable to follow and the `environment:` rules see no key to check. The
    string reaches the container as an argument, which is a superuser connection
    on the command line of the process that ships comment text to a third-party
    model provider.

    The mutation this kills is a rule that reads `environment:` only, which is
    where every other credential rule in this module looks.
    """
    document = {
        "services": {
            "worker": {
                "command": [
                    "alembic",
                    "-x",
                    "url=postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse",
                    "upgrade",
                    "head",
                ]
            }
        }
    }

    problems = credential_literals(SAMPLE_BASE_PATH, document, SAMPLE_SUPERUSER_LITERALS)

    assert problems, (
        "The superuser credential typed into `worker`'s command was not reported. It is not an "
        "`environment:` entry and it interpolates nothing, so it is invisible to every other "
        "credential rule in this module."
    )
    assert any(
        "worker" in problem for problem in problems
    ), f"The report does not name the service: {problems!r}."


def test_a_credential_literal_inside_a_health_check_list_is_caught() -> None:
    """The same string, four levels down, in the list `healthcheck.test` is.

    `healthcheck:` is a mapping, `test:` is a list, and the credential is inside
    one of its items — which is a shape no flat read of a service body reaches.
    `db`'s real health check has exactly this structure, and the control below
    proves the walk reaches into it on the real file rather than only on this
    one.

    The mutation this kills is a walk that descends into mappings and not into
    lists, which passes every test written against an `environment:` block and
    fails here.
    """
    document = {
        "services": {
            "worker": {
                "healthcheck": {
                    "test": [
                        "CMD-SHELL",
                        "psql postgresql://pulse_admin:replace-me-admin@db:5432/pulse -c 'select 1'",
                    ],
                    "interval": "30s",
                }
            }
        }
    }

    problems = credential_literals(SAMPLE_BASE_PATH, document, SAMPLE_SUPERUSER_LITERALS)

    assert problems, (
        "A credential nested inside `healthcheck.test` was not reported. The walk has to "
        "descend into lists as well as mappings: a health check command is a list, and so is "
        "every `command:` in the base file."
    )


def test_a_reference_to_the_credential_variable_is_not_reported_as_a_literal() -> None:
    """The other direction: `${DB_SUPERUSER}` is a name, and this rule reads values.

    Without this half, the obvious repair — searching for the variable *names* —
    would satisfy every assertion above while missing the literal that has no
    name in it, and it would fail `db`, which reads both variables by
    interpolation because that is how a deployment's real credential reaches
    Postgres.

    The reference route is not unguarded: it is
    `test_nothing_outside_the_database_service_reads_the_superuser_credential`,
    which follows `${...}` through `.env.example` transitively. The two rules
    read different things on purpose, and neither is the other's near miss.
    """
    document = {
        "services": {
            "db": {
                "environment": {
                    "POSTGRES_USER": "${DB_SUPERUSER:?DB_SUPERUSER is not set}",
                    "POSTGRES_PASSWORD": "${DB_SUPERUSER_PASSWORD:?not set}",
                }
            }
        }
    }

    problems = credential_literals(SAMPLE_BASE_PATH, document, SAMPLE_SUPERUSER_LITERALS)

    assert not problems, "\n".join(
        [
            "An interpolation was reported as a literal credential:",
            *problems,
            "",
            "`${DB_SUPERUSER}` is the name of a variable, not its value. `db` reads it that way "
            "in the real file, so a rule that flags it fails the stack doing exactly what "
            "ADR 0009 asks — and the repair somebody reaches for is to exempt `db`, which is "
            "how the literal route would then reopen on the one service nobody re-reads.",
        ]
    )


def test_the_string_walk_reaches_the_strings_a_real_service_nests(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """A control: the walk finds strings at every depth the real file uses.

    **A red here means these tests are broken, not the Compose files.** The rule
    above reports absence, and a walk that returns nothing reports the same
    absence — one that never descends into a list would pass over `db`'s health
    check and every `command:` in the file while reporting a clean stack.

    Three depths on real bodies, each a different nesting: a scalar directly
    under a service key, an item inside a list, and a value inside a mapping
    inside a mapping. `docs/MISTAKES.md` entry 35: find each mechanism on a
    subject that certainly has it.
    """
    assert base_compose, f"{base_compose_path} does not exist or declares nothing."

    services = services_of(base_compose)
    db_strings = service_strings(services.get(CREDENTIAL_OWNING_SERVICE) or {})
    worker_strings = service_strings(services.get("worker") or {})

    assert any("postgres:17" in text for text in db_strings), (
        f"The walk did not find `db`'s pinned image among {len(db_strings)} strings. That is a "
        "scalar directly under a service key — the shallowest thing there is — so a walk that "
        "misses it is not walking service bodies at all."
    )
    assert any("psql" in text for text in db_strings), (
        "The walk did not find `db`'s health check command. It lives inside the list under "
        "`healthcheck.test`, so a walk that descends into mappings but not into lists finds "
        "everything else here and misses every command in the file."
    )
    assert any("${DB_SUPERUSER" in text for text in db_strings), (
        "The walk did not find `db`'s POSTGRES_USER value, which is a string inside the "
        "`environment:` mapping inside the service mapping. It is also the string this rule "
        "must *not* report — see the interpolation test above — so finding it here and "
        "reporting nothing there is the pair that says the rule reads values rather than names."
    )
    assert any("celery" in text for text in worker_strings), (
        "The walk did not find `worker`'s command, which is a list of arguments. That is the "
        "exact shape the measured attack used."
    )


# ---------------------------------------------------------------------------
# What the second security review found: the configuration is not one file.
#
# Three more, all measured against the daemon. The first is the sharpest thing
# either review produced, because it defeats a fix the first round had just
# made: the guards read one document at a time, and Docker does not.
#
#   - A volume body written in the override redefines a volume the base file
#     mounts. `beat-schedule: {driver_opts: {type: none, device: /, o: bind}}`
#     added to the override's `volumes:` gives `beat` the host root, and the
#     per-file resolution saw the base file's empty body and called it an
#     ordinary Docker volume. 460 tests green, and the running container read
#     the host's `.env` through the mount.
#   - `ports` was an allowed service key whose value nothing read, so dropping
#     the `127.0.0.1:` prefix published Postgres on every interface.
#   - `build` was an allowed service key whose sub-keys nothing read, so
#     `additional_contexts` reached a directory outside the project — outside
#     `.dockerignore` too — and `build.privileged` ran the build as root on the
#     host.
#
# The shape they share is the one this module keeps meeting: a set is closed at
# one level and open at the next. The answer is the same each time, and the
# first of them adds a second rule to it — **read the configuration Docker
# assembles, not the file the line is written in**, wherever Docker assembles
# one. That is exactly one section today, and `merged_volume_bodies` is it.
# ---------------------------------------------------------------------------


def base_file_mounting_beat_schedule() -> tuple[Path, dict[str, Any]]:
    """The base file's real shape, reduced: `beat` mounts a volume declared empty."""
    return (
        SAMPLE_BASE_PATH,
        {
            "services": {"beat": {"volumes": ["beat-schedule:/var/lib/celery"]}},
            "volumes": {"beat-schedule": None},
        },
    )


def override_redefining(body: Any) -> tuple[Path, dict[str, Any]]:
    """The override, declaring nothing but a body for the volume the base file mounts."""
    return (SAMPLE_OVERRIDE_PATH, {"volumes": {"beat-schedule": body}})


def test_a_bind_carrying_volume_body_added_in_the_override_is_refused() -> None:
    """The second security review's HIGH: the two files are one configuration.

    `beat` mounts `beat-schedule`, which the base file declares with an empty
    body — an ordinary Docker volume, and the reason the base file passes every
    mount rule. Adding

        volumes:
          beat-schedule:
            driver_opts: {type: none, device: /, o: bind}

    to `docker-compose.override.yml` gives that container the host root. Nothing
    in the override mounts anything, so a rule that resolves a volume in the
    document that *mounts* it never looks at the file where the body is; and the
    base file's body is still empty, so a rule that resolves it there finds an
    ordinary volume. Measured against the daemon: 460 tests green, and the
    running container read the host's `.env` through the mount.

    It defeats the `name:`/`driver:` refusal the first fix round added, which is
    what makes it worth stating as a rule rather than a case: **a per-file read
    of a section Docker merges is not a read of the configuration.** Volume
    bodies are the one merged section this module reads, and
    `merged_volume_bodies` is where that is done.

    The mutation this must kill is the revert — `named_volume_source` looking up
    `top_level_volumes(document)` instead of the merged table. Both channels are
    asserted because the mount is both un-allowlisted and sensitive, and a
    reader that resolves it will say so twice; the union is asserted first
    because the property is that the attack does not pass, whichever rule
    catches it.
    """
    documents = (
        base_file_mounting_beat_schedule(),
        override_redefining({"driver_opts": {"type": "none", "device": "/", "o": "bind"}}),
    )

    problems = (
        unallowlisted_bind_mounts(documents)
        + sensitive_bind_mounts(documents)
        + unreadable_volume_declarations(documents)
    )
    assert problems, (
        "A volume body written in the override redefined a volume the base file mounts, and no "
        "rule objected. `docker compose up` merges the top-level `volumes:` section across both "
        "files before any service mounts anything, so `beat` gets the host root — measured, "
        "with the container reading the host's .env through it."
    )

    assert sensitive_bind_mounts(documents), (
        "The merged body resolves to a mount of `/` and the sensitive check did not report it. "
        "Both checks read the same resolved set, so a body the allowlist can see and the "
        "denylist cannot means the resolution is being done twice in two places."
    )
    assert any(
        "beat" in problem for problem in problems
    ), f"The refusal does not name the service that mounts the volume: {problems!r}."


def test_a_pre_created_volume_name_added_in_the_override_is_refused() -> None:
    """The same attack in the spelling the first fix round closed per-file.

    `beat-schedule: {name: precreated-host-root}` in the override attaches
    `beat`'s volume to a Docker volume created outside this stack, with no
    project prefix applied, and one `docker volume create --opt device=/` makes
    that the host root. The refusal for `name:` exists — E0-19's first review
    bought it — and it was reading the wrong document, which is the whole point
    of this finding: a fix at one level does not survive being asked about the
    wrong file.

    The mutation is the same revert, and this case is the one that shows the
    revert defeats an *existing* rule rather than only a new one.
    """
    documents = (
        base_file_mounting_beat_schedule(),
        override_redefining({"name": "precreated-host-root"}),
    )

    refusals = unreadable_volume_declarations(documents)

    assert refusals, (
        "A `name:` added to the override for a volume the base file mounts was not refused. "
        "What that volume is, is decided by a `docker volume create` that ran before this "
        "stack came up, and no reading of these files says what it mounts."
    )
    assert all(
        "beat-schedule" in refusal for refusal in refusals
    ), f"The refusal does not name the volume: {refusals!r}."


@pytest.mark.parametrize(
    ("shape", "body"),
    [
        ("a bind device", {"driver_opts": {"type": "none", "device": "/", "o": "bind"}}),
        ("a pre-created name", {"name": "precreated-host-root"}),
    ],
)
def test_the_same_volume_body_in_the_base_file_is_refused_too(shape: str, body: Any) -> None:
    """The control for the pair above: the rule is about the body, not about the file.

    **A red here means these tests are broken, not the Compose files.** Both
    tests above assert that a body written in the *override* is refused. If the
    merge were implemented as "the override always wins, and only the override
    is read", both would pass and the base file would be unguarded — which is
    the failure with the larger blast radius, since the base file is what every
    deployment runs.

    This was already green before the merge went in, and it has to stay green
    after: the same body in the file that mounts the volume is refused for the
    same reason.
    """
    path, document = base_file_mounting_beat_schedule()
    document = {**document, "volumes": {"beat-schedule": body}}

    documents = one_compose_file(path, document)
    problems = (
        unallowlisted_bind_mounts(documents)
        + sensitive_bind_mounts(documents)
        + unreadable_volume_declarations(documents)
    )

    assert problems, (
        f"{shape} written in the base file itself was not refused. The merge added in the "
        "second fix round must widen what is read, never move it: a body in the file that "
        "mounts the volume is the case that was already covered."
    )


def test_an_empty_merged_volume_body_is_not_a_bind() -> None:
    """The other direction: two files, both saying nothing, is still an ordinary volume.

    `beat-schedule` and `postgres-data` are declared empty in the base file, and
    the override says nothing about either. A merge that turned "no body" into
    something — a name, a device, a refusal — would fail the real stack on the
    two volumes it legitimately declares, and the repair somebody reaches for is
    an allowlist entry, which is a permission granted for a mount that does not
    exist.

    The mutation this kills is a merge that substitutes the volume's *name* when
    both bodies are empty, which is the shape a `dict.get` with a fallback
    takes.
    """
    documents = (base_file_mounting_beat_schedule(), override_redefining(None))

    mounts = declared_bind_mounts(documents)[(SAMPLE_BASE_PATH.name, "beat")]

    assert mounts.sources == frozenset(), (
        f"An empty merged body resolved to {sorted(mounts.sources)}. Neither file says anything "
        "about `beat-schedule` beyond its name, which is an ordinary Docker volume — it "
        "survives `docker compose restart beat` and it is not a piece of the host filesystem."
    )
    assert mounts.unreadable == (), (
        f"An empty merged body was refused as unreadable: {list(mounts.unreadable)}. That fails "
        "the real stack on `beat-schedule` and `postgres-data` both."
    )


def test_the_merged_volume_table_carries_what_each_file_declares(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """A control: the merge finds the real files' volumes, and the later body wins.

    **A red here means these tests are broken, not the Compose files.** The
    rules above report absence, and a merge that returned an empty table would
    make every named volume unresolvable — which is a refusal, so it would fail
    loudly rather than pass silently, but it would fail on the *wrong* thing and
    the repair would be to loosen the refusal.

    Two halves. The real files, where the table must carry both volumes the base
    file declares. And a synthetic pair where the override supplies a body for a
    name the base file declares empty, which is the case the finding is about
    and the one an implementation keyed on "first file wins" gets backwards.
    """
    assert base_compose and override_compose, (
        "A Compose file is missing or declares nothing, so the merged table is whatever "
        "survived and this control cannot tell that from a merge that drops entries."
    )

    real = merged_volume_bodies(
        (
            (base_compose_path, base_compose),
            (override_compose_path, override_compose),
        )
    )
    assert {"postgres-data", "beat-schedule"} <= set(real), (
        f"The merged table holds {sorted(real)}. The base file declares `postgres-data` and "
        "`beat-schedule`, and a table that does not carry them cannot resolve the mounts that "
        "name them."
    )

    merged = merged_volume_bodies(
        (
            base_file_mounting_beat_schedule(),
            override_redefining({"name": "precreated-host-root"}),
        )
    )
    assert merged.get("beat-schedule") == {"name": "precreated-host-root"}, (
        f"The merged body for `beat-schedule` is {merged.get('beat-schedule')!r}. The base file "
        "declares it empty and the override gives it a name, so the merged body is the "
        "override's — a merge that keeps the first declaration reads the empty body and calls "
        "the volume ordinary, which is the finding."
    )


def test_every_published_port_binds_a_loopback_address(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """A published port is reachable from this machine and from nothing else.

    `ports` is an allowed service key and no rule read its *value*, which is the
    same shape as `volumes:` being an allowed top-level section whose contents
    nothing resolved. The measurement is an omission rather than a wrong value:
    dropping the `127.0.0.1:` prefix from `db`'s entry in the override publishes
    Postgres on every interface — the laptop on a conference network serving its
    database to the room, which the override's own header comment already warns
    about — and the whole suite stayed green.

    **Both files**, although only the override publishes anything today. The
    base file must publish nothing at all and
    `test_base_compose_file_publishes_no_host_ports` says so; this rule is the
    weaker one that still holds if a port ever legitimately arrives there, and
    running it over both costs nothing while the base file publishes nothing.

    The mutation this must kill is that missing prefix. The near miss is `::1`,
    which is loopback in IPv6 and must pass — the address is bracketed in the
    short form, and a parser that splits on `:` without reading the brackets
    turns it into a host IP of `[`.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so it publishes nothing and a rule "
            "about where ports bind reports it clean."
        )

    published = [
        port
        for _, document in documents
        for body in services_of(document).values()
        for port in published_ports(body)
    ]
    assert published, (
        "No service in either Compose file publishes a port, so this rule has nothing to check "
        "and passes trivially. The development override publishes seven — the API, Postgres, "
        "Redis, two Mailpit ports and the two mock services — and a stack that publishes none "
        "of them is one no developer can reach. If publishing has moved somewhere this module "
        "does not read, point this rule at it rather than letting it pass over an empty list."
    )

    problems = [
        problem
        for path, document in documents
        for problem in non_loopback_publications(path, document)
    ]

    assert not problems, "\n".join(
        [
            "A service publishes a port on something other than loopback:",
            *problems,
            "",
            f"Allowed host addresses: {list(LOOPBACK_HOST_IPS)}. A `ports:` entry with no host "
            "address binds every interface on the machine, so `5432:5432` on a laptop serves "
            "the development database — superuser role included, since `.env` is the file the "
            "stack starts from — to every other machine on the network. Write the address: "
            "`127.0.0.1:5432:5432`.",
        ]
    )


@pytest.mark.parametrize(
    "spelling",
    ["5432:5432", "5432", "0.0.0.0:5432:5432", "192.168.1.10:5432:5432", "5432:5432/tcp"],
)
def test_a_port_published_off_loopback_is_refused(spelling: str) -> None:
    """Each way of publishing to the world, refused and named.

    `5432:5432` and a bare `5432` bind every interface — the second on a host
    port the daemon picks, which is no less published for being unpredictable.
    `0.0.0.0` says it out loud. A LAN address is the case someone writes on
    purpose to reach the stack from another machine, and it is the one this rule
    exists to make a decision rather than a habit. The `/tcp` suffix is there
    because a parser that does not strip it reads the protocol as part of the
    port.

    The mutation this kills is the rule's removal, and — for the first two
    cases — a check written as "if a host IP is present it must be loopback",
    which passes everything that names no address at all. That is the reading
    that makes the measured attack pass, because the attack is a *deleted*
    prefix.
    """
    document = {"services": {"db": {"ports": [spelling]}}}

    problems = non_loopback_publications(SAMPLE_OVERRIDE_PATH, document)

    assert problems, (
        f"`- {spelling}` on `db` was not refused. It binds an address this machine shares with "
        "the network it is on, and the database behind it is initialised from `.env`."
    )
    assert all(
        "db" in problem and spelling in problem for problem in problems
    ), f"The refusal does not name the service and the entry as written: {problems!r}."


@pytest.mark.parametrize(
    "entry",
    [
        "127.0.0.1:5432:5432",
        "127.0.0.1:5432:5432/tcp",
        "[::1]:5432:5432",
        {"target": 5432, "published": 5432, "host_ip": "127.0.0.1"},
        {"target": 5432, "published": 5432, "host_ip": "::1"},
    ],
)
def test_a_port_published_on_loopback_is_allowed(entry: Any) -> None:
    """The other direction, in every spelling — including the two the parser can break on.

    Without this half the rule is satisfied by refusing every published port,
    which would fail the real override on all seven of its entries and leave the
    repair as "delete the rule". The IPv6 case is the one that needs the
    bracket handling and the long form is the one that needs the `host_ip` key;
    a parser that reads neither refuses a correct file, which is how a guard
    gets deleted.
    """
    document = {"services": {"db": {"ports": [entry]}}}

    problems = non_loopback_publications(SAMPLE_OVERRIDE_PATH, document)

    assert not problems, "\n".join(
        [
            f"A port published on loopback was refused: {entry!r}",
            *problems,
            "",
            "127.0.0.1 and ::1 are both loopback, in the short form and the long one. A rule "
            "that refuses a correct entry is a rule someone deletes.",
        ]
    )


def test_the_port_reader_finds_the_address_of_every_published_port(
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """A control: the reader sees the real override's ports and reads their addresses.

    **A red here means these tests are broken, not the Compose files.** The rule
    above reports absence, and a reader that returns an empty list for every
    service reports the same absence. The override publishes seven ports and
    every one of them names `127.0.0.1`, so a reader that finds fewer than seven,
    or that reads the address as `None` on any of them, is not reading the file.
    """
    assert override_compose, f"{override_compose_path} does not exist or declares nothing."

    found = [
        (name, port)
        for name, body in sorted(services_of(override_compose).items())
        for port in published_ports(body)
    ]

    assert len(found) >= 7, (
        f"The reader found {len(found)} published ports in {override_compose_path.name}: "
        f"{found!r}. The override publishes the API, Postgres, Redis, two Mailpit ports and the "
        "two mock services — seven — and a reader that sees fewer is missing a spelling."
    )
    unread = [(name, port.spelling) for name, port in found if port.host_ip is None]
    assert not unread, (
        f"The reader could not read a host address for {unread!r}. Every entry in that file "
        "writes `127.0.0.1:` in front of the port, so an address read as `None` is a parser "
        "that cannot see one — which would make the rule above report the file clean by "
        "finding nothing rather than by finding loopback."
    )


def test_no_build_section_declares_a_key_this_module_cannot_read(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """The closed set one level inside `build:`, which was open. E0-19's second review.

    Admitting `build` admitted everything under it, and two sub-keys were
    measured going past every rule here with the suite green and a host file
    read out of the built image. `additional_contexts` names a second build
    context — any directory on the host, or a git URL — which a
    `COPY --from=<name>` then reads, and `.dockerignore` does not apply to it.
    `build.privileged` runs the build itself with host privileges, and it is a
    different key from the service-level `privileged:` that `PRIVILEGE_KEYS`
    refuses.

    Same answer as every other level: enumerate what the files use, refuse the
    rest. The mutation this must kill is either sub-key added to a `build:`
    section in either file.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing, so it declares no build sections and "
            "a rule about their keys reports it clean."
        )

    problems = [
        problem for path, document in documents for problem in unreadable_build_keys(path, document)
    ]

    assert not problems, "\n".join(
        [
            "A `build:` section declares a sub-key this module has not been taught to read:",
            *problems,
            "",
            f"Allowed today: {sorted(ALLOWED_BUILD_KEYS)}. A build reaches the host at image "
            "build time, which is before any rule about what a *container* may reach applies: "
            "`additional_contexts` reads a directory outside the project and outside "
            "`.dockerignore`, and `build.privileged` builds as root on the host. Teach this "
            "module the sub-key in the same change that adds it, and say why the rules above "
            "still hold over it.",
        ]
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("additional_contexts", {"host": "/"}),
        ("privileged", True),
        ("secrets", ["host-token"]),
        ("ssh", ["default"]),
    ],
)
def test_a_build_key_outside_the_closed_set_is_refused(key: str, value: Any) -> None:
    """The two that were measured, and two more the same argument covers.

    `additional_contexts: {host: /}` plus one `COPY --from=host` is the host
    filesystem inside the image, which is a bind mount that leaves no `volumes:`
    entry behind. `build.privileged` is the build running as root on the host.
    `secrets:` and `ssh:` forward a credential and an agent socket into the
    build; neither is used here and neither is read by anything in this module.

    The mutation this kills is adding any of them to `ALLOWED_BUILD_KEYS`, which
    is what a red here invites if the reason for the closed set is not written
    down. It is written down on the constant.
    """
    document = {"services": {"api": {"build": {"context": ".", key: value}}}}

    problems = unreadable_build_keys(SAMPLE_BASE_PATH, document)

    assert problems, (
        f"`build.{key}:` on `api` was not refused. Nothing in this module reads it, so whatever "
        "it reaches at build time is reached invisibly — and an image is where a container's "
        "filesystem comes from."
    )
    assert all(
        key in problem and "api" in problem for problem in problems
    ), f"The refusal does not name the sub-key and the service: {problems!r}."


def test_the_build_reader_finds_the_build_keys_the_compose_files_use(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """A control: the reader sees real `build:` sections, anchor-merged ones included.

    **A red here means these tests are broken, not the Compose files.** The rule
    above reports absence, and a reader that finds no build sections reports the
    same absence. `api`'s build comes from the `x-application` anchor and
    `mock-lms`'s is written in its own block, so finding both says the reader is
    reading the parsed document rather than the lines of the file — the same
    property the service-key control asserts one level out, and the same anchor
    that has twice been the route a finding took.
    """
    assert base_compose, f"{base_compose_path} does not exist or declares nothing."

    builds = build_keys_of(base_compose)
    assert builds, (
        "The reader found no `build:` section at all in the base Compose file. Five services "
        "build from a Dockerfile there, so an empty result is a reader that cannot see one."
    )

    assert set(builds.get(API_SERVICE, ())) == {"context", "dockerfile"}, (
        f"The reader says `{API_SERVICE}` builds with {sorted(builds.get(API_SERVICE, ()))}. Its "
        "build comes from the `x-application` anchor, so a reader that misses it is reading the "
        "file rather than the parsed document — and everything the anchor carries is then "
        "outside this rule."
    )
    assert set(builds.get("mock-lms", ())) == {"context", "dockerfile"}, (
        f"The reader says `mock-lms` builds with {sorted(builds.get('mock-lms', ()))}. That one "
        "is written in the service's own block, so finding the anchor's and missing this is a "
        "reader that only resolves merges."
    )


def test_the_closed_build_key_set_holds_no_key_the_compose_files_do_not_use(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """The other direction: the build set enumerates what exists, `args` included.

    `args` is the entry worth naming, because it is the one a reader assumes is
    there: a build usually has arguments, and this one does not. Admitting it
    for that reason is how `networks` got onto `ALLOWED_TOP_LEVEL_KEYS` — and a
    build argument is also a place a credential travels, which
    `test_nothing_outside_the_database_service_reads_the_superuser_credential`
    walks the document for. It comes back in the change that first needs one.
    """
    for path, document in (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    ):
        assert document, (
            f"{path} does not exist or declares nothing, so every entry would look unused and "
            "this test would report the constant as speculative when a file is what went."
        )

    declared = {
        key
        for document in (base_compose, override_compose)
        for keys in build_keys_of(document).values()
        for key in keys
    }
    unused = sorted(key for key in ALLOWED_BUILD_KEYS if key not in declared)

    assert not unused, "\n".join(
        [
            f"ALLOWED_BUILD_KEYS admits sub-keys no `build:` section declares: {unused}.",
            "",
            "A closed set that admits a feature the repository does not use is not closed; it "
            "is a smaller open one, with an entry nobody has had to think about.",
        ]
    )


# ---------------------------------------------------------------------------
# The identity provider's addresses reach the process that builds `Settings` —
# ticket E0-39, ADR 0077.
#
# ADR 0075 gave the five `oidc_*` settings defaults naming `mock-idp`, and the
# epic-boundary threat model found what that means: the base file starts that
# service in every deployment, so a deployment that sets none of them has a signing
# oracle for fake CARE and ADMIN identities and trusts it. ADR 0077 removes the
# defaults, which leaves the values needing a home — and the home is the one every
# other deployment-specific value that is an address rather than a credential
# already has, the `environment:` block of every service that builds a `Settings`,
# in the base file, interpolated so a deployment's own `.env` still wins.
#
# The other half of the move is `.env.example`, held by
# `tests/unit/test_env_example_resolves.py`; the refusal that makes removing the
# defaults worth doing is held by
# `tests/unit/test_oidc_provider_configuration.py`.
# ---------------------------------------------------------------------------

# The five variables E0-39 makes required, spelled as `tests/fixtures/doors.py`'s
# `door_contract` and `.env.example` already spell them. Named here rather than
# derived for the reason `SUPERUSER_VARIABLES` above is: they are the subject of
# the rule, and a sixth is a deliberate edit on this line.
OIDC_VARIABLES = (
    "OIDC_ISSUER",
    "OIDC_AUTHORIZATION_ENDPOINT",
    "OIDC_TOKEN_ENDPOINT",
    "OIDC_JWKS_URL",
    "OIDC_CLIENT_ID",
)

# The three services that construct `Settings`, and therefore the three a required
# setting stops from starting. `api` serves both doors; `worker` and `beat` build
# one identically — ADR 0042, and `tests/unit/test_config_settings.py`'s "`Settings`
# is constructed identically in `api`, `worker` and `beat`", which is the whole
# reason `CARE_DATABASE_URL` had to become optional rather than required.
SETTINGS_SERVICES = (API_SERVICE, *JOB_SERVICES)


def oidc_fallback_spelling(variable: str) -> re.Pattern[str]:
    """The one form E0-39 settles for these five entries: `${NAME:-<dev address>}`.

    Interpolated with a fallback, and nothing else. A bare literal is what a reader
    reaches for and it is refused here, because `environment:` beats `env_file:`: a
    literal overrides a deployment's own `.env` and makes the base file
    undeployable. Scope item 2 says so in as many words — "that is why the
    interpolated form is the decision, not a style choice".

    `${NAME}` with no fallback is refused too, for the reverse reason. On a checkout
    with no `.env` it interpolates to the empty string, and an empty `environment:`
    value *withdraws* the variable rather than leaving `env_file:` to supply it —
    the same mechanism the blanking lines above rely on — so the container refuses
    to start with the fallback one character away.

    The fallback's text is deliberately not pinned. It is the development stack's
    address, `.env.example` documents it, and a copy here would turn a change of
    development port into a test edit (`docs/MISTAKES.md` entry 19).
    """
    return re.compile(rf"^\$\{{{re.escape(variable)}:-(?P<fallback>\S.*)\}}$")


@pytest.mark.parametrize("service_name", SETTINGS_SERVICES)
def test_a_settings_building_service_is_given_the_identity_providers_addresses(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    service_name: str,
) -> None:
    """The five required settings reach every process that constructs `Settings`.

    E0-39 removes the defaults, so `Settings()` refuses to build without these five
    — and it is built the same way in all three of these services, so a stack that
    gives them to `api` alone comes up as an API with two containers in a restart
    loop. SPEC §14.3 asks that `docker compose up` from a clean checkout reach a
    launchable, loggable-into system, and this is the file that has to make that
    true now that nothing in the code does.

    **The base file, not the override**, and the asymmetry is the same one
    `test_services_inheriting_the_env_file_do_not_hold_the_superuser_credential`
    turns on: the base file is what every deployment runs and what CI's
    base-file-only pass runs alone, so a value present only in the override is
    absent from the stack that matters. The direction is the mirror image of the
    blanking rule — there, a value in the override is harmless and one in the base
    file is a defect; here, a value in the override is not enough.

    **The spelling is settled and asserted**, per `oidc_fallback_spelling` above:
    `${OIDC_ISSUER:-http://mock-idp:8000}`, so a deployment's own `.env` still wins
    and only the un-set case falls back to the development address — where layer 2's
    refusal then catches it outside development. A bare literal is refused here even
    though it would look right in the merged configuration, because it is the
    spelling that takes `.env` out of the picture.

    An entry declared with no value at all does not count either. `supplies_a_value`
    above reads that as a delivery, correctly, because for a credential the question
    is whether the host environment's copy reaches the container. The question here
    is the opposite one: a bare `OIDC_ISSUER:` passes through whatever the person
    running `docker compose up` happens to have exported, which on a clean checkout
    is nothing.

    **The mutation this kills:** the defaults removed from `app/config.py` and
    nothing put in their place, which is a stack that no longer comes up; the five
    given to `api` alone, which is two containers restarting; the five written into
    the override only, which comes up on a laptop and not in a deployment; and the
    literal form, which reads as done and makes the base file undeployable.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. A file that did not parse "
        "declares no environment for anybody, and a rule about what a service is given reports "
        "it missing rather than saying the file is gone."
    )

    body = services_of(base_compose).get(service_name)
    assert body is not None, (
        f"{base_compose_path} declares no `{service_name}` service, so there is nothing here to "
        f"configure. It declares {sorted(services_of(base_compose))}."
    )

    declared = service_environment(body)
    assert declared, (
        f"The reader finds no `environment:` entries at all on `{service_name}` (its body "
        f"declares {sorted(body)}). An unreadable environment block and a missing variable report "
        "the same emptiness, so this control comes first: all three of these services carry the "
        "shared anchor's blanking lines, and a reader that sees none of those cannot see these "
        "five either."
    )

    problems: list[str] = []
    for variable in OIDC_VARIABLES:
        if variable not in declared:
            problems.append(f"{variable} is not declared")
            continue
        value = declared[variable]
        if value is None:
            problems.append(
                f"{variable} is declared with no value, which passes through whatever the host "
                "environment happens to hold"
            )
            continue
        if not oidc_fallback_spelling(variable).match(value.strip()):
            problems.append(
                f"{variable} is declared as {value!r} rather than as "
                f"`${{{variable}:-<the development address>}}`"
            )

    assert not problems, "\n".join(
        [
            f"`{service_name}` is not given the identity provider in {base_compose_path.name}:",
            *problems,
            "",
            "E0-39 makes the five `oidc_*` settings required — a deployment that supplies no "
            "identity provider now stops at startup with a ConfigurationError naming the field, "
            "instead of quietly trusting the `mock-idp` container this file starts. The "
            "development values moved here as part of that change, so a stack whose base file "
            "does not carry them does not come up at all (SPEC §14.3).",
            "",
            "The interpolated form with a fallback is the decision rather than a style choice: "
            "`environment:` beats `env_file:`, so a bare literal would override a deployment's "
            "own `.env` and make this file undeployable.",
        ]
    )
