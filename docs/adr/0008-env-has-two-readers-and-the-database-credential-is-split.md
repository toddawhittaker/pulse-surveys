# 0008 — `.env` has two readers, and the database credential is split into parts

**Status:** Accepted
**Date:** 2026-08-12
**Tickets:** E0-02

## Context

E0-02 brings up Postgres. The official image is configured by `POSTGRES_USER`,
`POSTGRES_PASSWORD`, and `POSTGRES_DB` as three discrete values, and **Compose
cannot parse a URL** — its interpolation offers `${NAME}`, `${NAME:-default}`,
`${NAME:?error}`, and `${NAME:+alt}`, and nothing that splits a string. So the
credential inside `DATABASE_URL` cannot be handed to the database that
`DATABASE_URL` points at.

Three constraints already existed and none of them is negotiable here:

- **CI runs `cp .env.example .env` and then `docker compose up`**, in the
  `docker` job and in the e2e job both. That file has to be one the whole stack
  can start from, which is also why `DATABASE_URL` names the service `db`
  rather than `localhost`.
- **One credential in one place.** A second copy of the password that can drift
  out of step with the first was rejected before this ticket started.
- **No default credential in the base Compose file.** E0-02's definition of done
  names it as a security defect, because a working development password is a
  working production password.

[SPEC §13](../SPEC.md) mentions `.env.example` once, as
`# documented config surface (§6.3)`. [§6.3](../SPEC.md) enumerates an
*admin-facing* surface — term calendar, window timing, n-threshold, AI provider,
LTI registration — and never mentions a file or which process reads a line of
one. The spec is therefore silent on both questions this decision answers, and
a reasonable engineer might answer either one differently.

## Decision

**`.env` is one file with two readers**: `app.config.Settings` and the Compose
files. `Settings` sets `extra="ignore"` so a variable it does not read is not an
error, which is what makes one file possible.

**The database credential is stored in parts, and the URL is derived.**
`.env.example` declares `DB_USER`, `DB_PASSWORD`, and `DB_NAME`, and builds the
URL from them:

```
DATABASE_URL=postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}
```

Both readers expand those references, which was verified rather than assumed:
Compose expands them when it reads `.env` as its interpolation source, and
python-dotenv expands them for a developer running uvicorn on the host. The
password is written once. `docker-compose.yml` passes the three parts to `db` as
`${DB_USER:?…}`, `${DB_PASSWORD:?…}`, and `${DB_NAME:?…}` — required, never
defaulted, so a deployment that has set nothing stops with the variable named.

The application still reads `DATABASE_URL` and nothing else. The three parts are
inputs to the file, not settings, and no `Settings` field corresponds to them.

**A reader is established by finding one, never by naming one.** The sync test
in `tests/unit/test_env_example_sync.py` accepts an entry when a `Settings` field
resolves to it *or* when a Compose file interpolates its name, by parsing the
Compose files. Stop interpolating a name and the entry starts failing. A list of
exempt names would have moved the rot from `.env.example` into the test; see
[dispute E0-02-01](../disputes/E0-02-01.md), which settles that point and is the
reason this ADR exists to record the convention rather than the argument.

E0-14 and E0-16 inherit this: a mock LMS or mock IdP variable goes in the same
file and earns its place by being interpolated where the service is declared.

## Alternatives rejected

**A second copy of the password**, `DATABASE_URL` literal plus `POSTGRES_*`
entries. The obvious answer and the one this decision exists to avoid: two
values that must agree, no mechanism that makes them agree, and a failure that
surfaces as a connection refusal long after the edit that caused it.

**A default in the Compose file**, `${DB_PASSWORD:-pulse}` or a literal.
Rejected by E0-02's definition of done. A default credential in the base file is
inherited by every deployment that never sets one, and nothing reports it.

**A separate env file for Compose**, `docker/db.env` alongside `.env`. Rejected
because it does not solve the problem it appears to solve: the password would
live in that file *and* inside `DATABASE_URL` in `.env`, so it is the two-copies
option with an extra file. It also breaks `cp .env.example .env` as the single
setup step, which is what CI runs.

**Docker secrets and `POSTGRES_PASSWORD_FILE`.** The postgres image reads a
password from a file, and Compose can mount one as a secret. Rejected for the
same reason: the API still needs the password inside `DATABASE_URL`, so the
secret file is a second home for it rather than the only one. It also requires a
file that a fresh checkout does not contain, so the stack no longer starts from
a copied `.env.example`. Worth revisiting if real secret management arrives,
where the URL itself would come from the secret store whole.

**Splitting `.env` in two**, one file per reader. Rejected because the split is
not clean: `DATABASE_URL` is derived from variables that would sit in the other
file, so either the derivation crosses the boundary or the password does. Two
files also means two things to copy and two places to look, to enforce a
separation nothing needs.

**An entrypoint shim on `db` that parses `DATABASE_URL` in shell.** The only
route that keeps `.env.example` to exactly the `Settings` fields, and it fails
mechanically, not merely on taste. Variables exported by a custom entrypoint
live in that process; the `CMD-SHELL pg_isready -U "$POSTGRES_USER"` probe runs
as a separate exec that inherits the container's *configured* environment, which
would not contain them. The probe would need its own copy of the parser, or
would silently ask about a `postgres` role this stack never creates — a health
check that passes while meaning nothing, under a CI gate
(`scripts/ci/wait_for_health.sh`) built entirely on it meaning something. It
also puts hand-rolled string slicing on the credential path.

## Consequences

- **`.env.example` is no longer a list of application settings**, and a reader
  cannot tell from a line alone which process wants it. The entries say so in
  prose, and the test says so mechanically; neither is free.
- **Two consumers can now disagree about the same file.** The test parses the
  Compose files to check one direction, so a Compose file that stops parsing
  makes the test *stricter* rather than vacuous — that direction was chosen
  deliberately, and it is the property to preserve if the helper is ever moved.
- **Nothing checks that `DATABASE_URL` and the three parts stay consistent.** A
  hand-edited `.env` that hardcodes a different password in the URL than in
  `DB_PASSWORD` starts a stack whose API cannot log in to its own database. The
  interpolation makes the mistake unlikely rather than impossible, and the
  failure is loud and immediate.
- **The convention has to be taught once per new service.** E0-14 and E0-16 add
  variables for the mock LMS and mock IdP, and the rule they must follow —
  interpolate the name where the service is declared — is enforced by a test
  whose failure message says it.
- **This does not settle how production supplies configuration.** §10 puts
  secrets in the environment or a secret store, and the process environment
  overrides `.env` for both readers. This decision governs the development and
  CI path, which is the only one that exists today.
