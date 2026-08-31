# 0087 — `/healthz` and `/dev` keep disclosing the environment, on one verdict

**Status:** Accepted
**Date:** 2026-08-26
**Ticket:** [E1-14](../tickets/e1/E1-14-healthz-dev-verdict.md), closing the
carried entry
[`docs/tickets/e1/carried-from-e0.md`](../tickets/e1/carried-from-e0.md)
("`/healthz` tells an unauthenticated caller which environment this is").

## Context

`GET /healthz` (`backend/app/api/health.py`) answers `settings.environment` to
any unauthenticated caller. That value is what every environment-keyed guard in
this system rests on: whether `/docs` and `/openapi.json` are served
([ADR 0074](0074-the-openapi-schema-is-served-only-in-development.md), which
also gates SQL echo in `app/db.py`), whether the developer console answers
anything other than `404` ([ADR 0079](0079-the-developer-console-is-gated-in-the-handler.md)),
whether the login cookie carries `Secure`
([ADR 0078](0078-the-login-state-cookie-is-signed-per-process-and-short-lived.md)),
and whether the demo seed will run at all
([ADR 0063](0063-the-demo-seed-runs-only-in-a-development-environment.md)).
Publishing the name opens none of those guards; it tells a caller which one to
try first.

`/dev` discloses the same fact through a second door. ADR 0079 gates the page in
the handler rather than at route registration, so the router answers a method
mismatch before the handler ever runs: measured against the pinned Starlette
(1.6.0) with `ENVIRONMENT=production`, `GET /dev` → `404` and `POST /dev` →
`405` with `Allow: GET`, while `POST` to a path this application never
registers → `404`. ADR 0079's own consequences section names this as an open
observation — "nothing in the suite asserts anything about another method on
this route" — and says explicitly that whoever closes it does so alongside
whatever decides `/healthz`.

The carried entry's done-when asks for one of three honest answers — drop the
field, gate it, or keep it with a record of why the guard list above is
acceptable to publish — and asks that the same verdict reach the `405`.

## Decision

**Keep the `/healthz` `environment` field, and leave `/dev` exactly as
measured.** The `405` on `POST /dev` outside development is within the
disclosure this record accepts, and ADR 0079's decision stands unamended
beyond the note this record adds to it.

The environment name is not a secret. Its only consumer today is an
orchestrator's health check (`docker-compose.yml`'s `healthcheck:` blocks,
`Makefile`'s `healthz` target), and the value is `production` in production,
which surprises nobody who can already reach the deployment. Naming the guard
list above does not weaken any guard on it: `/docs`, `/dev`, the cookie's
`Secure` attribute, SQL echo, and the demo seed each still have to be reached
and passed in their own right, on their own mechanism, regardless of whether a
caller already knew which environment they were probing. Knowing the name
shortens a caller's search; it does not open a door.

## Alternatives rejected

**Drop the field.** The cleanest cut, and the one that costs the most for a
disclosure that is not itself a hole: the orchestrator health check and
`README.md`'s documented `/healthz` response would both need to change in the
same PR, and the field has genuine operational value — an operator curling a
deployed `/healthz` learns whether it is pointed at the environment they think
it is. Rejected because there is nothing behind the field to protect; removing
it pays a real operational cost against a disclosure that opens no guard.

**Gate it behind authentication.** The consistent answer once a session model
exists, and not available here: `/healthz` and `/dev` are both scaffold-era
routes with no authenticated request in front of them (the same reasoning ADR
0074 and ADR 0079 each give for rejecting an authenticated gate on `/docs` and
the console), and E1's session work is what would have to land first. Rejected
for the same reason ADR 0079 rejects it for `/dev` — this is a decision for
whichever epic gives observability surfaces a real auth model, not a
prerequisite this ticket should build to answer a question that costs nothing
left open.

## Consequences

- The disclosure is now pinned as accepted-and-known in both places it
  arrives, by three tests: `test_healthz_does_not_report_an_earlier_apps_cached_environment`
  and the two existing `/healthz` tests it joins in `tests/unit/test_healthz.py`,
  and `test_post_to_the_dev_console_answers_405_with_allow_get_outside_development`
  plus its unregistered-path control in
  `tests/unit/test_dev_console_exposure.py`. A regression that made the
  disclosure worse (a `/healthz` field that leaked more than the environment
  name) and a change that silently "fixed" it (a `POST /dev` that started
  answering `404`, or a `/healthz` that stopped naming the environment) would
  both now be caught, where before neither direction was guarded.
- Nothing changes in `backend/app/api/health.py` or `backend/app/api/dev.py`.
  The behaviour these routes ship was already what the carried entry measured;
  this record is the choice to keep it, not a code change.
- The orchestrator health check and the `README.md:51` line describing
  `/healthz`'s response both keep working unchanged.
- ADR 0079 is amended, not superseded: its decision to gate `/dev` in the
  handler stands, and this record settles the open method-mismatch note in its
  decision section — see the amendment there.
