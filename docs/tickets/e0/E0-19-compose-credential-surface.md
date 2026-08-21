# E0-19 — Compose credential surface (Batch G)

**ID:** E0-19
**Branch:** `e0/compose-credential-surface`
**Depends on:** E0-02, E0-03

## Status — what is left here

**Built as written.** This ticket is already one coherent batch — four routes
to the same ADR 0009 bound, all landing in
`tests/unit/test_compose_stack.py` and `tests/unit/test_env_example_resolves.py`
— so nothing moves out of it and nothing moves in.

Re-verified on the epic branch 2026-08-21, with current locations:
`SENSITIVE_BIND_SOURCES` is still a seven-entry denylist
(`test_compose_stack.py:379`), `ALLOWED_TOP_LEVEL_KEYS` is
`("name", "services", "volumes")` (line 249) and bounds which sections may
appear rather than what an allowed section may carry, `bind_sources` (line
1644) reads only service-level bind entries and feeds only the relative
privilege comparison (line 2091), and nothing resolves a named volume through
`driver_opts`.

## Context

ADR 0009 sanctions a Postgres superuser identity and bounds it: the
application containers must never hold that credential, because a superuser
role bypasses every grant and row-level security, which would make the whole
identity separation scheme in §4.1 decorative. `docker-compose.yml` enforces
that bound by blanking `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD` on every
service that inherits `.env`.

E0-03 spent five reviewer passes hardening the tests that guard that bound.
They now hold against the credential named directly, named in another key's
value, reached through `.env` indirection, inherited through `extends`,
delivered by a top-level `secrets:` entry, or carried in by an `include:`d
file — the last closed by *closing the set*: any top-level section the module
cannot read is refused, so a new Compose feature fails loudly instead of
bypassing silently.

Pass 5 found that the closed set bounds which sections may appear and not what
an allowed section may carry — and `volumes:` is allowed. This ticket closes
that and the related routes found in the same pass. The first three routes
below were **demonstrated against the running daemon** during E0-03's review
with the whole suite green; the fourth was found by reading and is only
partially measured — the item says which half.

Read first: `docs/adr/0009`, SPEC §4.1, and the module docstring of
`tests/unit/test_compose_stack.py`, which records the reasoning the five
passes produced.

## The one decision, made first

Three of the four routes end at the same design question, so answer it before
writing any of them: **what may each service mount, stated as an allowlist in
absolute, normalised form.**

- One structure, something like `ALLOWED_BIND_MOUNTS: {(file, service):
  {normalised sources}}` — keyed by file because the asymmetry E0-03's
  blanking rule needed applies here too: what the base file may mount is not
  what the development override may mount, since the override is absent from
  every deployment. Today's legitimate entries are few (the override's reload
  mount of `./backend`, `db`'s `./scripts/db-init`); enumerate what exists,
  nothing speculative.
- **Normalisation is the entry condition for the comparison, both sides.**
  Compose resolves a relative bind source against the **project directory** —
  where the Compose file is — and not against the service's `working_dir`
  (measured during E0-03's review with `working_dir: /opt/app`, no effect).
  Normalise against the project directory, collapse `.` segments and doubled
  separators, then compare. Normalising against the wrong base clears a mount
  that reaches the host and rejects one that does not.
- **`SENSITIVE_BIND_SOURCES` stays**, as defence in depth behind the
  allowlist: a socket path that somehow enters the allowlist should still fail
  the sensitive check by name. Both checks run over the same normalised set.

With that decided, the four routes are one coherent change plus one extension:

## Scope

### 1. A host-mount allowlist rather than a denylist

Adding `- ./:/app/repo:ro` to `worker` — the edit someone makes to get
`alembic/` or `scripts/` into the job container — passes every test today, and
hands that container the entire `.env` the `environment:` block just blanked:
`.env` sits beside `docker-compose.yml` in every deployment, because
`env_file: - .env` requires it. Blanking two variables is worth nothing if the
file they came from is mounted. **Done when** any bind source not in the
allowlist fails a test that names the mount and says why the project directory
in particular is fatal (`.env` lives there).

### 2. Resolve named volumes through `driver_opts`

`- /var/run/docker.sock:...` on `worker` is caught. The identical mount
declared as a top-level named volume with `driver_opts: {type: none, device:
/var/run/docker.sock, o: bind}` is not, because the service entry names a
volume rather than a path — and the docker socket is root on the host for the
container E0-13 runs untrusted comment text through. Any `device:` works,
including `/` and the project directory, which makes this a second spelling of
route 1. **Done when** `bind_sources` (or a sibling it feeds) resolves a
service's named volumes through the top-level `volumes:` section and treats a
bind-type `device:` as a bind source, so the same declaration fails the same
tests under either spelling — allowlist and sensitive check both.

### 3. The literal-value route through `.env.example`

`transitively_read` follows `${...}` references; a documented entry whose
value contains the credential **as a literal** — e.g.
`ALEMBIC_DATABASE_URL=postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse`
— is followed by nothing, so naming it in a Compose file passes. In CI this is
sharp: the workflow does `cp .env.example .env`, so the placeholder *is* the
value, and CI would itself run the superuser credential in three containers.
`tests/unit/test_env_example_resolves.py` already compares resolved values,
but only for `DATABASE_URL`. **Done when** every documented entry that any
Compose file delivers to a non-`db` service is resolved and checked for the
superuser role name and password as substrings — the same comparison the
`DATABASE_URL` tests make, generalised to the delivered set rather than one
name. The delivered set is computed from the Compose files, not hand-listed
(`docs/MISTAKES.md` entry 35's rule: an inventory must come from somewhere the
guarded structure cannot shrink).

### 4. Normalise a bind source before matching it

The measurement so far: `/var/run/./docker.sock` and `//var/run/docker.sock`
both survive verbatim into `docker compose config`, so the denylist comparison
misses them; a relative source such as `- ../secret:/x:ro` is likewise
compared as spelled. The *reachability* half — that the alternate spellings
actually mount — was found by reading, not run: **measure it against the
daemon before building**, and record the measurement in the test's docstring.
This route is answered by the normalisation rule in the decision above rather
than by a fourth denylist entry. **Done when** a sensitive or un-allowlisted
source spelled with a `.` segment, a doubled separator, or relatively fails
the same tests as its canonical spelling.

### 5. An ADR for the constraints E0-03 imposed

Three of them: the closed top-level key set, the outright refusal of
`extends:`, and the rule that the repository root may hold no Compose-named
file this suite does not read. They constrain everyone who edits a Compose
file from now on, and their reasoning lives in a test module docstring — the
one place the person they constrain has no reason to open. An E0-04 author
adding `secrets:` for a Docker-secret migration credential gets a red test
from a module they did not touch and no record of why; an author renaming
`docker-compose.yml` to Docker's preferred `compose.yaml` gets the same
surprise from the third rule. The contestable alternative is the same for all
three and must be recorded: read whichever Compose-named files and sections
exist and run every rule against all of them, which needs no ban. The spec is
silent and the choice is contestable — exactly the ADR test. Take the next
free ADR number at build time; this ticket also extends what the module
refuses (the allowlist), so the ADR covers the new rule in the same breath.

## Out of scope

- Broadening any rule to a *new* Compose feature by enumeration. The closed
  set is the strategy; a feature this repository does not use stays refused
  rather than modelled. If a later ticket needs `secrets:`, that ticket
  teaches the module to read it, in the same pull request.
- Redis broker authentication and the Celery task-return-value logging
  policy. Both were raised during E0-03 and both are E3's, recorded in pull
  request #16.

## Acceptance criteria

- [ ] Adding `- ./:/app/repo:ro` to any application service fails a test
      naming the mount and saying that `.env` lives in that directory.
- [ ] The docker socket mounted through a top-level named volume with
      `driver_opts` fails the same tests that catch it as a direct bind.
- [ ] A documented `.env.example` value containing the superuser role name or
      password as a literal fails when any Compose file delivers that variable
      to a service other than `db`, and the checked set of variables is
      derived from the Compose files rather than hand-listed.
- [ ] A sensitive or un-allowlisted bind source spelled with a redundant
      separator, a `.` segment, or relatively still fails; the reachability of
      the alternate spellings is measured against the daemon and the
      measurement recorded.
- [ ] The base-file/override asymmetry is decided once, stated where the
      allowlist lives, and tested in both directions (an override-only mount
      in the base file fails; the override's legitimate mounts pass).
- [ ] Every rule is verified by mutation, and the set includes the nearest
      passing case, not only the obvious failure — for the allowlist, that is
      a mount one path segment away from an allowed one.
- [ ] The ADR records the three closed-set rules plus the allowlist, with the
      read-everything alternative and why it lost.

## Definition of done

**Tests apply**, and they are most of the ticket. **Docs apply** — the ADR.
**AI evals and accessibility do not apply.** **Security review applies and is
not light:** every item is a route to the ADR 0009 bound, and each was green
against the full suite when found. The review should try spellings this ticket
did not think of — the point of the allowlist-plus-normalisation shape is that
a spelling nobody anticipated must fail closed, and that property is what the
reviewer is best placed to attack.
