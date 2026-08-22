# 0076 — What a Compose file may say is a closed set

**Status:** Accepted, and **amended before merge on 2026-08-21 by E0-19's own
security review**, which measured the decision below wrong in one direction: it
claimed every surface the guards read is a closed set, and the *service* level —
where nearly every host-reaching Compose key lives — was not one at all. Five
rules are seven, one of them reverses a decision this record made, and the
review's measurements are in the consequences.
**Date:** 2026-08-21
**Tickets:** E0-03 (rules 1 to 3, decided there), E0-19 (recorded here, and rules 4 to 7)

## Context

[ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
sanctions a Postgres superuser identity and bounds it: no application container
may hold that credential, because a superuser role bypasses every grant and
every row-level policy, which would make the §4.1 identity separation
decorative. `docker-compose.yml` enforces the bound with two hand-written lines
that blank `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD` on every service that
inherits `.env`, and `tests/unit/test_compose_stack.py` is what holds those
lines up.

E0-03's five reviewer passes each found the same hole one spelling further out:
the credential inside another key's *value*, then one hop through `.env`, then
`extends:`, then `include:`, then a top-level `secrets:` entry. The verdict was
that this was structural rather than bad luck — every guard was anchored to a
hand-picked subtree of a hand-picked pair of files, so each round added one more
place to look and the next spelling was always just outside it. E0-19 found two
more of the same shape in the same module: a bind mount of the project
directory, which hands a container the whole `.env` the `environment:` block
just took two variables out of, and the identical mount hidden behind a named
volume's `driver_opts`.

E0-19's own security review then found it a sixth time, one level in. The
closed top-level key set bounds which *sections* may appear and says nothing
about what a service body may carry, so `volumes_from: - db` on `worker` — every
mount `db` has, which is the whole Postgres data directory — passed the entire
suite green. Four more service keys were measured going past just as quietly.
That is the finding this record is amended for, and it is the same lesson at a
smaller radius: a closed set is a claim about exactly one level.

SPEC §7.2 names the services the stack runs and says nothing about which Compose
features a file may use, so the choice is this record's. It needs to exist
because the rules below constrain everyone who edits a Compose file from now on,
and their reasoning lives in a test module docstring — the one place the person
they constrain has no reason to open. An E0-04 author adding `secrets:` for a
Docker-secret migration credential gets a red test from a module they did not
touch; so does an author renaming `docker-compose.yml` to Docker's preferred
`compose.yaml`. This is the record they find.

## Decision

**Every surface the guards read is a closed set — at every level, not just the
outermost — and a shape the module cannot read is refused rather than ignored.**
Seven rules, all the same move:

| # | The set that is closed | What that refuses |
|---|---|---|
| 1 | `ALLOWED_TOP_LEVEL_KEYS` — `name`, `services`, `volumes`, plus `x-` extension fields | `include:` moves configuration into a file nothing here parses; `secrets:` and `configs:` name a variable without interpolating it |
| 2 | `extends:` — no service may use it | `extends: {service: db}` inherits the one service exempt from the credential rule; the `file:` form points at an unparsed document, per service, with no top-level section to notice |
| 3 | `COMPOSE_FILE_NAMES` — the root holds exactly the two files this suite reads | Docker prefers `compose.yaml` over `docker-compose.yml`, so a third file replaces the stack every rule here describes while every test stays green |
| 4 | `ALLOWED_SERVICE_KEYS` — the ten keys a *service body* may declare | `volumes_from:`, which grants one container every mount another has; `cgroup:`, `uts:`, `runtime:` and `develop:`, each measured passing the pre-amendment guards; and the sixth nobody has thought of |
| 5 | `ALLOWED_BIND_MOUNTS` — the host paths a service may bind, keyed by `(file, service)` | `- ./:/app/repo:ro`, which mounts the directory `.env` lives in, and every other mount nobody enumerated |
| 6 | `READABLE_VOLUME_KEYS` — `driver_opts` and `labels` — and the bind-`driver_opts` shapes | The docker socket declared as `driver_opts: {type: none, device: /var/run/docker.sock, o: bind}`; any shape this module cannot classify; and, separately, the three keys that say *defined elsewhere* — `external:`, `name:` and `driver:` |
| 7 | `PRIVILEGE_KEYS` with `ALLOWED_PRIVILEGE_GRANTS` — no service declares a privilege key, absolutely, unless an entry names the file, the service and the key | `privileged: true`, `pid: host`, `network_mode: host`, `userns_mode: host`, `devices:` and `cap_add:` on any service in either file |

**Where a set cannot be closed, the walk is exhaustive instead.** The credential
rules follow `${...}` references, so a credential *typed out* rather than
referenced is invisible to them, and `command:`, `entrypoint:`,
`healthcheck.test`, `labels:` and `build.args` are all strings that reach a
container. Enumerating those keys would be the same mistake as enumerating the
routes above, so every string anywhere in a service body is walked, keys as well
as values, at any depth, on every service including `db`. The rule is the same
one stated the other way round: never a list of the places somebody thought of.

Four properties of rules 4 to 7 are part of the decision rather than of the
implementation.

**Normalisation is the entry condition for the comparison, on both sides.** One
helper normalises the sources read out of a file, the entries of
`ALLOWED_BIND_MOUNTS`, and `SENSITIVE_BIND_SOURCES`. A rule that normalises one
side rejects a mount that reaches nothing and clears one that reaches the host.
It is purely textual — no filesystem access — and a relative source resolves
against the project directory, which was measured against the daemon rather than
reasoned about.

**The allowlist is keyed by file, because the two files are not symmetric**, and
it is the same asymmetry the blanking rule turns on: `./backend` mounted over
the installed wheel is a development convenience in the override and a defect in
the base file.

**The allowlist is an inventory of what exists, never speculative.** Four
entries today. A fifth is a deliberate edit, reviewed as one, and an entry no
file uses is itself a failure. `ALLOWED_SERVICE_KEYS` is the same, with one
trap: it is enumerated from the documents *as the parser sees them*, after
PyYAML has resolved the `<<:` merges, so it is three keys longer than the
visible lines of the base file. A list written by reading the file fails the
base file on its own anchor.

**An exception ships as a validated structure, and empty.**
`ALLOWED_PRIVILEGE_GRANTS` holds nothing, because no service in either file
declares a privilege key. It exists because the alternative to an exception
structure is an exception written into the rule, which is one nobody has to
justify: an entry here names the file, the service and the key, carries its
reason as the value, and a test refuses an entry for a key the named service
does not actually declare — so a permission cannot outlive its grant.

`SENSITIVE_BIND_SOURCES` stays behind rule 5 as defence in depth: a path that
somehow enters the allowlist should still fail by name. It is absolute over both
files rather than a comparison against `api`, for the reason recorded below. The
full reasoning for all seven rules, including the measurements, is in the module
docstring and the comment above each constant in
`tests/unit/test_compose_stack.py`; this record does not repeat it.

## Alternatives rejected

**Read whichever Compose-named files and sections exist, and run every rule
against all of them.** The genuine competitor, and it is the same one for all
seven rules: it needs no ban, it never fails a legitimate change, and it is what
anyone proposes first. It lost on two counts.

*A feature the module cannot read would fail silently instead of loudly.*
Running the credential rules over a section whose meaning they do not model
reports clean, which is indistinguishable from safe. `include:` names a file
this module does not open; a `secrets:` entry names a variable without
interpolating it, so a walker looking for the credential in values finds
nothing; an unclassifiable `driver_opts` contributes no source, and a rule
phrased over sources alone reads that as a service mounting nothing. Each of
those is a green test over an unexamined route.

*Modelling every Compose feature is an open-ended obligation.* It has to be
done for features this repository does not use, right the first time, and kept
right as Compose grows. The closed set converts that standing obligation into a
deliberate, per-feature decision, made once, in the pull request that actually
needs the feature and by the person who knows why.

**A longer denylist of paths nobody may mount** (rules 5 and 6 only). What
E0-03 shipped, and the thing E0-19 replaced. A denylist is a list of the
spellings somebody thought of; the five reviewer passes above are the
measurement of how that goes. `- ./:/app/repo:ro` is on no denylist anyone
would write, and it is the mount someone reaches for to get `alembic/` into the
job container.

**Comparing each job service's privilege against `api` rather than ruling
absolutely** (rule 7). *This was the decision until 2026-08-21, and the review
overruled it.* The argument for it was good: E0-03's requirement is "no more
than the API image", the API service is the reference every other service is
built from, and a comparison needs no exception list because raising `api` is a
visible act. It has a hole. The override merges `x-development-source` into all
three application services, so **one line on the shared anchor grants all three
at once** and a rule asking whether `worker` has more than `api` sees nothing —
measured with the whole suite green for `privileged: true`, `pid: host`,
`network_mode: host`, `userns_mode: host`, `devices:` and `cap_add: SYS_ADMIN`.
Any rule phrased as a difference between two services in one file is defeated by
whatever both of them inherit. The absolute rule costs the exception structure
above, which is the price of not having that hole.

**Admitting `name:` and `driver:` on a named volume as inert metadata** (rule 6).
What this record shipped in the morning, and the review took it apart with the
record's own sentence. `external: true` is refused because the volume is created
somewhere this file cannot see — and that is true of all three. A `name:`
attaches the volume to a **pre-created** Docker volume under exactly that name
with no project prefix, and `docker volume create --opt device=/ --opt o=bind
--opt type=none` is one command away; a `driver:` hands the mount to a plugin
that decides what it is. Both are refused now, with the message the third one
gets.

## Consequences

**A closed set that stops one level short reports clean over everything that
level carries, and this record made that mistake before it was a day old.** The
first version of the decision above said "every surface the guards read is a
closed set" while the service body — where `volumes_from`, `cgroup`, `uts`,
`runtime`, `develop` and every privilege key live — was open. All five of those
keys were written into a service and run past the guards as they then stood:
five green suites, and `volumes_from: - db` alone gives `worker` every mount `db`
has, which is the entire Postgres data directory. The mount rules read
`volumes:` and there was nothing named there to read. So the question to ask of
a closed set is not whether it is closed but **what a member of it carries that
nothing reads** — and the answer has to be re-asked at each level down.

**A red test arrives from a module the author did not touch, and rule 4 makes
that routine.** Adding `secrets:`, renaming the base file, mounting a new host
path, or giving a service an ordinary key like `restart:` or `deploy:` fails
`tests/unit/test_compose_stack.py`. Each failure message names the constant, says
that the module must be extended in the same change, and — for rule 5 — says why
the project directory in particular is fatal. That surprise is the cost these
rules exist to impose, and this record is what the author should be pointed at.

**A later ticket needing a new Compose feature teaches the module to read it, in
the same pull request**, and says beside the new entry why the credential rules
still hold over it. Adding the key alone is not the change.

**Three limits are accepted rather than closed.** Normalisation is textual, so a
`~` or `${HOST_DIR}` source normalises to something no allowlist entry matches
and is refused — the safe direction, and not a resolution. `COMPOSE_FILE_NAMES`
is a claim about Docker's behaviour, not about this repository: it is the one
thing here that can go stale with nobody touching the tree, so a Compose release
recognising a ninth name makes rule 3 wrong silently — re-check it against the
Compose release notes, not against the tests. And the string walk searches for
the credential's *documented* value, the placeholder `.env.example` resolves to,
so it catches the committed placeholder and cannot see a real deployment
password typed into a Compose file. Nothing in this repository knows that value,
which is why the limit is stated rather than fixed.

**None of this sees a merged document.** The suite parses raw YAML, one file at
a time, never merged, which is what makes the base-file/override asymmetry
visible at all. Anything that exists only after Compose merges the two files is
outside every rule above.
