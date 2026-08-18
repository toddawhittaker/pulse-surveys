# 0065 — The demo institution registers a fictional platform, and not the mock LMS

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-17

**Leaves [ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md)
standing unamended**, which is the whole point of it.

## Context

[ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md) argues that
`mock-lms` is safe in the base Compose file on four properties, and the fourth is
the one that carries the weight: "A tool only trusts it if a registration says
so. A launch from this platform is worth exactly as much as the row in
`lti_platform` naming its issuer. A production Pulse with no such row rejects
every launch it signs, and that is the boundary that actually matters." That
record is true today because **no such row exists anywhere in this repository.**

E0-17 states the hazard directly: "Seeding an `lti_platform` row for the mock LMS
is what would make ADR 0038 wrong… If this script registers the mock, the
registration must be unreachable from a deployed environment, and ADR 0038 needs
amending to say how."

The seed cannot avoid the table altogether. Its people are `person` rows, a
`person` is linked to a `user` ([ADR 0064](0064-the-demo-seed-is-idempotent-by-natural-key.md)
explains why every demo person is), `user.lti_platform_id` is `NOT NULL`, and
`user_identity` is where the demo's only email addresses live — which E0-17's
security review asks to be unroutable and which the integration suite asserts
exist. So *a* registration is written. The question is which.

## Decision

`scripts/seed.py` registers one platform, and it is invented:

| Column | Value |
|---|---|
| `issuer` | `https://lms.pulse-demo.invalid` |
| `client_id` | `pulse-demo-tool` |
| `jwks_url` | `https://lms.pulse-demo.invalid/.well-known/jwks.json` |
| `jwks_fetched_at` | `NULL` |

`.invalid` is reserved by RFC 2606 precisely so that a name cannot belong to
anybody. The host resolves nowhere, the JWKS URL fetches nothing, and no process
in this repository or outside it holds a key that would let a launch claiming
this issuer verify. It is a registration that identifies the demo institution's
own people and authorises no launch at all.

**`mock-lms` is not registered by this or any other path in the repository.**
ADR 0038's fourth property therefore still holds as written, and that record is
untouched.

The `ENVIRONMENT` guard ([ADR 0063](0063-the-demo-seed-runs-only-in-a-development-environment.md))
sits above this in any case, so even the fictional row cannot be written by a
deployed run. The two are independent on purpose: the guard is about where the
script may run, and this is about what it may write.

## Alternatives rejected

**Register `mock-lms`, guarded by the environment check.** The obvious answer,
and the one E0-17 explicitly permits. It loses because it moves the boundary ADR
0038 rests on from "a fact about the repository" to "a fact about a script's
control flow". Today the argument a reviewer can check is *grep the repository
for the issuer and find nothing*; afterwards it would be *read `scripts/seed.py`
and satisfy yourself the guard cannot be bypassed*, forever, including by
everyone who edits that file later. ADR 0038 would have to be amended to say the
guard is what enforces it, and a Compose-level safety claim resting on a Python
`if` is a worse claim than the one it replaced.

**Register `mock-lms` from a separate script that only a developer runs.** Same
weakness with an extra file: the row still exists in the repository, and the
grep-for-the-issuer check still comes back positive. It also splits the demo
institution's setup across two commands, which is the thing `make seed` exists
not to do.

**Write no registration, and no `user`/`user_identity` rows with it.** Would keep
`lti_platform` empty, which is the strongest version of ADR 0038's claim.
Rejected because it takes the identity split out of the demo institution
altogether: `user_identity` is the table SPEC §4.1 protects with a database
grant, and a demo with no rows in it gives E9, E10 and E0-18 nothing to develop
the separation against. It also fails
`test_no_seeded_person_carries_a_routable_email_address`, which asserts the
address sweep is non-empty rather than passing over an absence.

**Use `example.edu` rather than `.invalid`.** Also reserved (RFC 2606) and also
safe, and `.invalid` is the stronger signal: `example.edu` reads as a
placeholder somebody might substitute, `.invalid` reads as a name that is not
supposed to work. `mock-lms/app/seed.py` made the same choice for the same
reason.

## Consequences

**E0-18 needs a registration for the mock and does not get one here.** Its scope
is "first Playwright paths through launch and web login", and a launch from
`mock-lms` will be rejected by a Pulse with no row naming its issuer — which is
exactly ADR 0038's design working. Whoever builds E0-18 has to decide where that
row comes from and how it is kept out of a deployment, and this record and ADR
0038 are what that decision is held against. It is named in E0-17's pull request
as deferred rather than left to be discovered.

**A grep for `mock-lms:8000` across the repository still returns only the Compose
files and the mock's own source**, and that is the check a reviewer should make
on any future change to this script. `tests/integration/test_demo_seed_script.py`
makes the same check against the seeded database, with the matcher run against
four real platform issuers first so that it cannot pass by matching nothing.

**The demo institution cannot be launched into.** Nobody can complete an LTI
launch as a seeded person, because the platform they belong to does not exist.
That is the intended state until E0-18, and it is worth saying out loud so that
the next person reads it as a decision rather than as a bug.
