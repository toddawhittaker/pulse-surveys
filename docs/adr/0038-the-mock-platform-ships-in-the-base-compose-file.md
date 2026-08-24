# 0038 — The mock platform ships in the base Compose file, and is kept out of a deployment by what it holds

**Status:** Accepted, amended 2026-08-19 by
[ADR 0068](0068-the-demo-seed-registers-the-mock-platform-behind-its-guard.md)
**Date:** 2026-08-16
**Tickets:** E0-14, E0-31

## Context

Two things in E0-14 pull in opposite directions.

[SPEC §7.2](../SPEC.md) lists `mock-lms` among the services the stack runs, and
`tests/unit/test_mock_lms_service.py` asserts it is declared in
`docker-compose.yml` — the base file, read on its own with no override merged
over it. The reason that test reads the base file is the same one
`tests/unit/test_compose_stack.py` was written for: `docker compose up` merges
`docker-compose.override.yml` automatically, so a service declared only there
comes up on a laptop and in every merged CI pass and nowhere else.

E0-14's definition of done says the opposite-sounding thing: "review that the
mock cannot be reached from a deployed environment". A service in the base file
comes up in every deployment that runs the base file.

## Decision

`mock-lms` is declared in `docker-compose.yml`, not behind a Compose profile.
What keeps it out of a deployment is not the Compose file, and this record says
so plainly so that nobody reads the base-file declaration as a claim of safety:

- **It holds nothing.** No database credential, no `env_file:`, no volume, no
  network access to anything. Its whole state is a key generated for one process
  and two invented users.
- **It reaches nothing.** It has no `depends_on`, no database, no broker. It
  posts a form at whatever URL it was configured with, and it will never be
  configured with a real one.
- **It publishes no port.** `expose:` documents 8000 on the Compose network; the
  development override is what binds 8080 on the host, and that override is the
  file no deployment reads.
- **A tool only trusts it if a registration says so.** A launch from this
  platform is worth exactly as much as the row in `lti_platform` naming its
  issuer. A production Pulse with no such row rejects every launch it signs, and
  that is the boundary that actually matters.

  **Amended 2026-08-19 (E0-31 item 1).** One thing in this repository now writes
  that row: `seed_mock_platform` in `scripts/seed.py`, so that E0-18 can drive a
  real launch. **What keeps it out of a deployment is the demo seed's own
  environment guard** — the script refuses to run unless `ENVIRONMENT` resolves
  to `development` (ADR 0063), and that check is evaluated again at the
  registration itself rather than only at start-up. So this property no longer
  reads "no such row exists anywhere in this repository"; it reads "no run
  permitted to write it can start". ADR 0068 records the decision, what it
  costs, and the two questions that replace the grep a reviewer used to make.

## Alternatives rejected

**A Compose profile (`profiles: [dev]`).** The obvious answer, and it loses more
than it buys. It contradicts §7.2, which lists the service in the stack. It
changes a committed test, which makes it a dispute rather than an implementation
choice. And it takes `mock-lms` out of the base-file-only pass in CI
([ADR 0011](0011-ci-validates-the-image-by-running-the-base-compose-file-alone.md))
— the one pass that runs what actually ships — so the image would be built by CI
and never started by it.

**Declaring it only in `docker-compose.override.yml`.** Same loss, plus it fails
the committed test, plus §9.2 asks that both entry doors be exercised in every
run and E0-18's end-to-end paths need the platform in whatever CI brings up.

**A separate `docker-compose.mocks.yml` a developer opts into.** A third Compose
file to keep in step with two, and `tests/unit/test_compose_stack.py` deliberately
holds a closed list of the Compose file names this repository may contain, for
reasons written there.

## Consequences

**The boundary is a property of the deployment, not of this repository.** Anyone
deploying Pulse for real deploys a subset of these services behind their own
orchestration; §7.2 already says the reverse proxy is out of scope for this file.
This record is what a reviewer should hold that decision against.

**If Pulse ever ships a "run the whole compose file" deployment path**, this
record becomes wrong and the profile question reopens — with the spec edit §7.2
would then need.

**A registration for it now exists, and its safety is a property of a Python
guard.** That is a weaker claim than the one this record shipped with, and ADR
0068 says so plainly rather than presenting it as equivalent. The reviewer's
check moves from "grep the repository for the issuer and find nothing" to "does
anything other than `seed_mock_platform` write it, and does that function still
read the environment first".

**The service is a signing oracle for its own fake identity, reachable by anyone
who can reach the container.** It authenticates nobody: it will sign a launch as
either seeded user for whoever asks. That is the intended behaviour of a test
platform and it is precisely why the four properties above have to keep holding.
