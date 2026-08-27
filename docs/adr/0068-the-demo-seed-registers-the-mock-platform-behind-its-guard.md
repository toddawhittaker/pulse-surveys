# 0068 — The demo seed registers the mock platform, behind the guard it already had

**Status:** Accepted
**Date:** 2026-08-19
**Tickets:** E0-31

**Supersedes the registration half of
[ADR 0065](0065-the-demo-institution-registers-a-fictional-platform.md)**, and
amends [ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md),
which no longer stands unamended.

## Context

ADR 0038 argues that `mock-lms` is safe in the base Compose file on four
properties, and the fourth carries the weight: a tool trusts that platform only
if a row in `lti_platform` names its issuer, so a production Pulse with no such
row rejects every launch it signs.

ADR 0065 kept that property true the strongest way available — by registering a
*fictional* platform for the demo institution's people, at an RFC 2606
`.invalid` address nobody holds a key for — and named the cost in its own
consequences: "E0-18 needs a registration for the mock and does not get one
here."

E0-31 item 1 is that cost arriving. E0-18 is the ticket that proves E0's exit
criterion, it drives a real launch from `mock-lms`, and until something
registers that issuer the launch is rejected — which is ADR 0038's design
working exactly as intended, and is why the row could not simply be added by
whoever noticed. It is the only item in E0-19 to E0-37 that blocks the epic
exit.

**ADR 0065 rejected this decision explicitly**, and its reason is right and is
the cost being paid here: it moves the boundary from *a fact about the
repository* — grep for the issuer and find nothing — to *a fact about a script's
control flow*, which every future editor of that script has to preserve. Todd
settled the mechanism on 2026-08-18.

## Decision

`scripts/seed.py` registers the mock platform, with the deployment a launch
carries:

| Column | Value |
|---|---|
| `issuer` | `http://mock-lms:8000` |
| `client_id` | `mock-lms-client` |
| `jwks_url` | `http://mock-lms:8000/.well-known/jwks.json` |
| `jwks_fetched_at` | `NULL` |
| `lti_deployment.deployment_id` | `mock-lms-deployment-1` |

These are the literal values `docker-compose.yml` configures the service with
([ADR 0037](0037-the-mock-platform-is-configured-by-compose-literals.md)), held
as constants in the script because it runs where that file may not be, and
asserted equal to it by a test.

**What keeps the row out of a deployment is the guard the script already
carried, and nothing else**: it refuses to run unless `ENVIRONMENT` resolves to
`development` ([ADR 0063](0063-the-demo-seed-runs-only-in-a-development-environment.md)).
No new mechanism is invented. That rule was disputed, arbitrated and settled by
Todd in [E0-17-01](../disputes/E0-17-01.md), which is the reason to reuse it
rather than to design a second control that has been argued through once.

Three things make that a control a reviewer can check rather than a claim:

- **`seed_mock_platform` evaluates the guard at the row**, not only in `main`.
  `main` is what actually stops a deployed run, before a connection is opened;
  checking again at the write is what makes the dependency structural, so no
  ordering of calls in the file and no future caller of `seed` reaches the
  registration without the environment having been read.
- **A test calls `seed` directly with a deployed-looking configuration** and
  asserts the registration is absent, with the control written on the same
  database immediately afterwards so that an empty table cannot pass for a
  refusal. It is the only test in the suite that goes red if the guard at the
  row is deleted, because a subprocess can only ever observe `main` refusing.
- **A test compares the seeded values against the platform's own configuration**,
  so the two copies of the mock's identity cannot drift into a launch that fails
  its audience check with nothing naming the files that disagree. Two sources,
  because the key-set URL is not a Compose literal — the platform composes it
  from its own issuer and `mock-lms/app/config.py`'s `JWKS_PATH` — and a guard
  whose whole inventory was the Compose `environment:` block could never see it.
- **A test asserts that no `user` row belongs to the mock's registration.** That
  property is what stops a trusted issuer which authenticates nobody from being a
  login oracle for a real purview, and it is the one thing here that a later
  ticket could undo in two lines while every other test stayed green.

**ADR 0065's fictional registration stays.** The demo institution's eighteen
people go on belonging to `https://lms.pulse-demo.invalid`, and the mock
registration carries no `user` rows at all. The two do different jobs: one gives
the demo institution an identity split to develop against, the other lets a
launch reach the code.

**Amended in part by
[ADR 0097](0097-the-identity-a-verified-subject-resolves-to.md) (E1-12).** The
fourth bullet above, and the sentence about the mock registration carrying no
`user` rows, were true until that ticket. E1-12 makes the reachable set on that
registration **exactly two named subjects** — the two-hat person and a dean —
because the dual-door identity merge and SPEC §7.3's leadership limb have to be
demonstrable on the running stack and in E1-15's browser proof. The property
argued for here is narrowed rather than removed: the test named above still
exists, now as an equality against a written-down inventory rather than against
the empty set, so a third subject is a red. ADR 0097 states what a launch as
either of them reaches on a development box, and why the guard above is what
bounds it.

## Alternatives rejected

**Keep ADR 0065 and let E0-18 create the row itself.** The row exists either
way; this puts it behind a Playwright fixture instead of behind the guard, which
is strictly worse — a fixture is not a thing a deployment refuses to run, and
the registration would then live in `tests/` where no reviewer looks for a
production hazard.

**A second control of its own** — a Compose profile, a separate script, a
dedicated flag, a distinct environment variable for this row. Rejected on the
ground the decision was made on: the rule that keeps a destructive seed out of a
deployment has been disputed and settled once, and a second rule beside it is
two things to keep in step and a second thing to get wrong
(`docs/MISTAKES.md` entry 13). ADR 0065 rejected the separate-script variant
already, for the additional reason that it splits `make seed` in two.

**Register the mock from a migration.** A migration runs in every environment by
definition, which is the one property this row must not have.

**Leave E0-18 unable to launch and move the exit criterion.** SPEC §14.3 makes
E0's exit a launchable-into system. Declining the row means declining the exit.

## Consequences

**The check a reviewer makes changes, and this record is where the new one is
written down.** A grep for `mock-lms:8000` across the repository now returns the
seed as well as the Compose files and the mock's own source, so that grep no
longer answers the question on its own. What replaces it is two questions:
*does anything other than `seed_mock_platform` write a registration naming the
mock*, and *does that function still check the environment before it writes*.
Both are asserted by `tests/integration/test_demo_seed_script.py`.

**The residual gap of E0-17-01 is inherited, and it is larger than it was.** An
operator who exports a production `DATABASE_URL` over a development checkout
seeds a production database, because the guard reads the environment name and
the address independently. That was accepted by decision rather than closed, and
what such a run now writes includes a registration for a platform that
authenticates nobody and will sign a launch as any user for whoever can reach
it. Closing it means constraining the address and the environment name together,
which is a change to ADR 0063 and not to this record. **It is owned rather than
merely disclosed**: the epic README's "Carried out of E0" table has a row for it,
with E13 as the owner and a done-when, because that table exists precisely
because a deferral recorded only where it was deferred is one nobody picks up.

**The `jwks_url` this writes is plaintext, and that is a forward cost rather
than an exposure.** `http://mock-lms:8000/.well-known/jwks.json` is a container
name on the Compose network with no certificate anywhere. Nothing reads the
column yet, and an attacker positioned to intercept that fetch could reach the
mock directly and have it sign anything, so the plaintext buys them nothing. What
it does do is constrain E1: E0-24 item 1 has E1 decide what a legitimate
`jwks_url` looks like, and a rule requiring `https` would reject this row and
break E0-18. E0-24 item 1 now says so, so that E1 designs the carve-out rather
than adding one under pressure to get a gate green.

**E0-18 gets past the registration boundary and no further.** A launch from the
mock arrives as one of *its* two invented subjects, not as one of the eighteen
demo people, and nothing here turns such a subject into a Pulse person. That is
launch-time provisioning, which SPEC §14.3 gives to E1, so E0-18 still owns the
question of what its Playwright path lands on.

**If Pulse ever ships a "run the whole compose file" deployment path**, ADR 0038
already says that record becomes wrong. This one becomes wrong with it, and
sooner: such a path would run a stack containing the platform *and* a seed
command an operator might reach for.
