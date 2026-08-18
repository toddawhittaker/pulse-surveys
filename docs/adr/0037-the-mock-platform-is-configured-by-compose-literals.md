# 0037 — The mock platform is configured by Compose literals, and earns no `.env.example` entry

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-14

## Context

The mock platform reads five values: its issuer, its client ID, its deployment
ID, where its launch form posts, and the `target_link_uri` it signs. E0-14's
sixth acceptance criterion requires the launch target in particular to be
configuration rather than a constant, "so it can point at the tool once E1
exists".

The repository has an exact rule about the configuration surface, from
[ADR 0008](0008-env-has-two-readers-and-the-database-credential-is-split.md) and
the epic README: an `.env.example` entry earns its place because an
`app.config.Settings` field resolves to it, or because a Compose file
interpolates it as `${NAME}`. `tests/unit/test_env_example_sync.py` enforces both
directions — an undocumented interpolation fails, and a documented variable
nothing reads fails.

That rule leaves E0-14 a genuine choice, because the mock's settings class is not
`app.config.Settings`. Interpolating in Compose would *require* five
`.env.example` entries; not interpolating would forbid them.

## Decision

The five values are **literals in the `mock-lms` service's `environment:` block**
in `docker-compose.yml`, and `.env.example` gains nothing.
`mock-lms/app/config.py` defaults to the same values, so the platform starts with
no configuration at all.

## Alternatives rejected

**`${MOCK_LMS_TOOL_LOGIN_URL:-...}` and five `.env.example` entries.** This is
the shape the rule permits, and it puts five variables for a development-only
fake platform into the file that documents the *application's* configuration
surface — the one an operator reads to deploy Pulse. Each of those five has
exactly one correct value on the Compose network, so every one of them is a knob
with one setting, which `CLAUDE.md` says not to build.

**A settings file mounted into the container.** A second configuration mechanism
in a repository that has exactly one, for a service that needs five strings.

**Constants in the source, with no environment at all.** Fails the sixth
criterion, and deservedly: pointing the mock at a differently-addressed tool
would mean editing and rebuilding the image.

**Values on the launch page as query parameters.** Makes every launch's target
attacker-controlled, in a service whose whole job is to sign things.

## Consequences

**Two places hold the same five values** — the Compose block and the defaults in
`config.py` — and they can drift. Both are stated to agree, in comments on each
side, and the Compose file is named as authoritative for a deployment. The
defaults exist because they must: the test fixture starts this application with
an empty environment, and so does `uvicorn app.main:create_app --factory` on a
laptop.

**Changing where the mock points is a Compose edit, not an `.env` edit.** That is
a small ergonomic loss for an operator and a real gain for the `.env.example`
rule, which is only useful for as long as every entry in it has a reader.

**E0-16's mock IdP faced the same choice and reached the same answer**, for the
same reasons: its three values are literals in the `mock-idp` service's
`environment:` block, `mock-idp/app/config.py` defaults to the same three, and
`.env.example` gained nothing. See
[0058](0058-the-mock-provider-publishes-its-registration-and-its-seed.md) for
where a client learns the two of them it needs.
`tests/unit/test_env_example_sync.py`'s docstring anticipated both tickets:
"E0-14 and E0-16 add readers to the Compose files and need no edit here."

**If a later ticket does need one of these values in `.env`** — a public base URL
for a tunnelled demo is the plausible case — then it becomes an interpolation and
gains its `.env.example` entry in the same change, and this record is amended
rather than worked around.
