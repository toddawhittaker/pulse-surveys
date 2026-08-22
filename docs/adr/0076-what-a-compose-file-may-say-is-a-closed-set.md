# 0076 — What a Compose file may say is a closed set

**Status:** Accepted
**Date:** 2026-08-21
**Tickets:** E0-03 (rules 1 to 3, decided there), E0-19 (recorded here, and rules 4 and 5)

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

SPEC §7.2 names the services the stack runs and says nothing about which Compose
features a file may use, so the choice is this record's. It needs to exist
because the rules below constrain everyone who edits a Compose file from now on,
and their reasoning lives in a test module docstring — the one place the person
they constrain has no reason to open. An E0-04 author adding `secrets:` for a
Docker-secret migration credential gets a red test from a module they did not
touch; so does an author renaming `docker-compose.yml` to Docker's preferred
`compose.yaml`. This is the record they find.

## Decision

**Every surface the guards read is a closed set, and a shape the module cannot
read is refused rather than ignored.** Five rules, all the same move:

| # | The set that is closed | What that refuses |
|---|---|---|
| 1 | `ALLOWED_TOP_LEVEL_KEYS` — `name`, `services`, `volumes`, plus `x-` extension fields | `include:` moves configuration into a file nothing here parses; `secrets:` and `configs:` name a variable without interpolating it |
| 2 | `extends:` — no service may use it | `extends: {service: db}` inherits the one service exempt from the credential rule; the `file:` form points at an unparsed document, per service, with no top-level section to notice |
| 3 | `COMPOSE_FILE_NAMES` — the root holds exactly the two files this suite reads | Docker prefers `compose.yaml` over `docker-compose.yml`, so a third file replaces the stack every rule here describes while every test stays green |
| 4 | `ALLOWED_BIND_MOUNTS` — the host paths a service may bind, keyed by `(file, service)` | `- ./:/app/repo:ro`, which mounts the directory `.env` lives in, and every other mount nobody enumerated |
| 5 | `READABLE_VOLUME_KEYS` and the bind-`driver_opts` shapes — how a named volume is resolved to a host path | The docker socket declared as `driver_opts: {type: none, device: /var/run/docker.sock, o: bind}`, and any volume shape this module cannot classify, `external: true` and an `nfs` device included |

Three properties of rules 4 and 5 are part of the decision rather than of the
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
file uses is itself a failure.

`SENSITIVE_BIND_SOURCES` stays behind rule 4 as defence in depth: a path that
somehow enters the allowlist should still fail by name. The full reasoning for
all five rules, including the measurements, is in the module docstring and the
comment above each constant in `tests/unit/test_compose_stack.py`; this record
does not repeat it.

## Alternatives rejected

**Read whichever Compose-named files and sections exist, and run every rule
against all of them.** The genuine competitor, and it is the same one for all
five rules: it needs no ban, it never fails a legitimate change, and it is what
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

**A longer denylist of paths nobody may mount** (rules 4 and 5 only). What
E0-03 shipped, and the thing E0-19 replaced. A denylist is a list of the
spellings somebody thought of; the five reviewer passes above are the
measurement of how that goes. `- ./:/app/repo:ro` is on no denylist anyone
would write, and it is the mount someone reaches for to get `alembic/` into the
job container.

## Consequences

**A red test arrives from a module the author did not touch.** Adding
`secrets:`, renaming the base file, or mounting a new host path fails
`tests/unit/test_compose_stack.py`. Each failure message names the constant, says
that the module must be extended in the same change, and — for rule 4 — says why
the project directory in particular is fatal. That surprise is the cost these
rules exist to impose, and this record is what the author should be pointed at.

**A later ticket needing a new Compose feature teaches the module to read it, in
the same pull request**, and says beside the new entry why the credential rules
still hold over it. Adding the key alone is not the change.

**Two limits are accepted rather than closed.** Normalisation is textual, so a
`~` or `${HOST_DIR}` source normalises to something no allowlist entry matches
and is refused — the safe direction, and not a resolution. And
`COMPOSE_FILE_NAMES` is a claim about Docker's behaviour, not about this
repository: it is the one thing here that can go stale with nobody touching the
tree, so a Compose release recognising a ninth name makes rule 3 wrong silently.
Re-check it against the Compose release notes, not against the tests.

**None of this sees a merged document.** The suite parses raw YAML, one file at
a time, never merged, which is what makes the base-file/override asymmetry
visible at all. Anything that exists only after Compose merges the two files is
outside every rule above.
