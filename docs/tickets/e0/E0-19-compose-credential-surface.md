# E0-19 — Compose credential surface

**ID:** E0-19
**Branch:** `e0/compose-credential-surface`
**Depends on:** E0-02, E0-03

## Context

ADR 0009 sanctions a Postgres superuser identity and bounds it: the application
containers must never hold that credential, because a superuser role bypasses
every grant and row-level security, which would make the whole identity
separation scheme in §4.1 decorative. `docker-compose.yml` enforces that bound
by blanking `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD` on every service that
inherits `.env`.

E0-03 spent five reviewer passes hardening the tests that guard that bound, and
they now hold against a large set of routes: the credential named directly, named
in another key's value, reached through one or more hops of `.env` indirection,
inherited through `extends`, delivered by a top-level `secrets:` entry, or
carried in by a file pulled in with `include:`. The last of those was closed by
*closing the set* — `tests/unit/test_compose_stack.py` refuses any top-level
section it cannot read, so a new Compose feature is a decision that fails loudly
rather than a silent bypass.

Reviewer pass 5 found that the closed set bounds **which sections may appear**
and not **what an allowed section may carry**, and `volumes:` is allowed. This
ticket closes that, and two related routes found in the same pass. It is a
separate ticket because it is a coherent subject in its own right and because
E0-03 was a ticket about Celery.

Read first: `docs/adr/0009`, SPEC §4.1, and the module docstring of
`tests/unit/test_compose_stack.py`, which records the reasoning the five passes
produced.

## Scope

Each of these was demonstrated against the running daemon during E0-03's review,
with the whole suite green. They are not hypotheticals.

- **A host-mount allowlist rather than a denylist.** `SENSITIVE_BIND_SOURCES`
  enumerates bad sources. Adding `- ./:/app/repo:ro` to `worker` — the edit
  someone makes to get `alembic/` or `scripts/` into the job container — passes
  every test today, and hands that container the entire `.env` the `environment:`
  block just blanked. `.env` sits beside `docker-compose.yml` in every
  deployment, because `env_file: - .env` requires it. Blanking two variables is
  worth nothing if the file they came from is mounted. State the mounts a service
  may have; reject the rest.
- **Resolve named volumes through `driver_opts`.** `- /var/run/docker.sock:...`
  on `worker` is caught. The identical mount declared as a top-level named volume
  with `driver_opts: {type: none, device: /var/run/docker.sock, o: bind}` is not,
  because the service entry names a volume rather than a path. That is root on the
  host for the container E0-13 will run untrusted comment text through. Any
  `device:` works, including `/` and the project directory, which makes this a
  second route to the item above.
- **The literal-value route through `.env.example`.** `transitively_read` follows
  `${...}` references. A documented entry whose value contains the credential as a
  literal — `ALEMBIC_DATABASE_URL=postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse`
  — is followed by nothing, so naming it in the Compose file passes. In CI this is
  sharper than elsewhere: the workflow does `cp .env.example .env`, so the
  placeholder *is* the value, and CI would itself run the superuser credential in
  three containers. `tests/unit/test_env_example_resolves.py` already compares
  resolved values, but only for `DATABASE_URL`; extend it to every documented
  entry a Compose file delivers to a non-`db` container.
- **Normalise a bind source before matching it.** `SENSITIVE_BIND_SOURCES` is
  compared against the string as declared, so the same location under another
  spelling misses: `/var/run/docker.sock` is caught, while `/var/run/./docker.sock`,
  `//var/run/docker.sock`, and a relative path climbing out of a service's
  `working_dir` are not. This is the same class as the allowlist item above and
  probably wants the same answer rather than a fourth denylist entry.

- **An ADR for the constraints E0-03 imposed.** The closed top-level key set and
  the outright refusal of `extends:` constrain everyone who edits a Compose file
  from now on, and the reasoning lives in a test module docstring — the one place
  the person it constrains has no reason to open. An E0-04 author adding
  `secrets:` for a Docker-secret migration credential gets a red test from a
  module they did not touch and no record of why. The spec is silent and the
  choice is contestable: a reasonable engineer would teach the module to read
  those sections rather than ban them. E0-03 wrote ADR 0011 for a smaller
  decision than this one.

## Out of scope

- Broadening any rule to a *new* Compose feature by enumeration. The closed set
  is the strategy; a feature this repository does not use should stay refused
  rather than modelled. If a later ticket needs `secrets:`, that ticket teaches
  the module to read it, in the same pull request.
- Redis broker authentication and the Celery task-return-value logging policy.
  Both were raised during E0-03 and both are E3's, recorded in pull request #16.

## Acceptance criteria

- [ ] Adding `- ./:/app/repo:ro` to any application service fails a test naming
      the mount and saying that `.env` lives in that directory.
- [ ] The docker socket mounted through a top-level named volume with
      `driver_opts` fails the same test that catches it as a direct bind.
- [ ] A documented `.env.example` value containing the superuser role name or
      password as a literal fails, when a Compose file delivers that variable to
      any service other than `db`.
- [ ] Each rule is verified by mutation, and the mutation set includes the
      nearest passing case, not only the obvious failure.
- [ ] A sensitive bind source spelled with a redundant separator, a `.` segment,
      or relatively still fails.
- [ ] `docs/adr/NNNN` records the closed-set decision, with the alternatives.

## One decision to make once, not twice by accident

The mount allowlist and the `driver_opts` resolution both touch `bind_sources`,
which today feeds only the *relative* privilege comparison — "does this service
take anything `api` does not". An allowlist needs the absolute form, and with it
the same asymmetry the blanking rule needed in E0-03: what the base file may
mount is not what the development override may mount, because the override is
absent from every deployment. Decide that once, explicitly, and say so where the
rule lives.

## Definition of done

**Tests apply**, and they are most of the ticket.

**Docs apply** — the ADR above.

**AI evals, accessibility do not apply.**

**Security review applies and is not light.** Every item here is a route to the
ADR 0009 bound, and each one was green against the full suite when it was found.
