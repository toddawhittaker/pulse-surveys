# 0075 — The two doors' addresses are settings, and every default is the development stack

**Status:** Accepted
**Date:** 2026-08-21
**Ticket:** [E0-18](../tickets/e0/E0-18-e0-exit-smoke.md)

## Context

Both entry doors need addresses the tool did not have. The launch door needs the
platform's browser-facing authorization endpoint and its own public base URL, and
the web door needs the identity provider's issuer, its browser-facing authorize
URL, its server-facing token endpoint and key set, and this tool's client id.

Two things make where they live a real question rather than an obvious one.

**`lti_platform` has no column for an authorization endpoint**, and that is
deliberate: `backend/app/models/lti.py` says the two OIDC endpoints "arrive with
the code that calls them, in the same change, rather than as columns nothing
writes", and E0-23 confirmed that service-address columns belong to E1.

**Every address is one of two horizons.** On the development stack a browser on
the host reaches these services at `localhost:8000/8080/8081`, and the `api`
container reaches them as `api`, `mock-lms` and `mock-idp`. A value the browser
is redirected to and a value the tool fetches are therefore different strings for
the same service.

[SPEC §6.3](../SPEC.md) enumerates the configuration surface and names none of
these, so the spec is silent and a reasonable engineer would differ — chiefly on
whether they should be defaulted at all, since `app/config.py`'s own module
docstring says deployment wiring has no default because "a working literal
default is a misconfiguration that starts successfully and is wrong in
production".

## Decision

**Seven `Settings` fields, all defaulted to this repository's own development
stack**, each documented in `.env.example` in the same change:
`PUBLIC_BASE_URL`, `LTI_PLATFORM_AUTHORIZATION_ENDPOINT`, `OIDC_ISSUER`,
`OIDC_AUTHORIZATION_ENDPOINT`, `OIDC_TOKEN_ENDPOINT`, `OIDC_JWKS_URL` and
`OIDC_CLIENT_ID`. The horizon is decided per value, not per service.

The defaults are not the "working literal default" that docstring refuses.
`http://mock-idp:8000` and `http://localhost:8080` resolve nowhere but on this
stack, so a deployment that forgets one gets a door that fails at its first hop —
loudly, at the point of use — rather than a system that starts and is quietly
pointed somewhere plausible and wrong.

What they buy is E0's own exit criterion. §14.3 asks that `docker compose up`
from a clean checkout yield a launchable, loggable-into system; CI does
`cp .env.example .env` and brings the stack up. Required fields would work
equally well there, because `.env.example` carries the values either way — but a
developer running `uvicorn` on the host against a half-written `.env` would get a
startup refusal naming seven variables whose only correct value is the one this
repository already knows.

The development wiring that has to agree with `PUBLIC_BASE_URL` lives in
`docker-compose.override.yml`, not in the base file: `MOCK_LMS_TOOL_LOGIN_URL`,
`MOCK_LMS_TOOL_LAUNCH_URL` and `MOCK_IDP_TOOL_REDIRECT_URI` are repointed at
`localhost:8000`. This settles E0-30 item 3.

## Alternatives rejected, and what each costs

**Columns on `lti_platform` now.** The right long-term home for the platform's
authorization endpoint — it is a property of a registration, not of a
deployment, and a second registered platform would need a second value. Rejected
because E0-23 already decided the columns are E1's and because E0 registers one
platform; adding a column here would mean a migration, a model change and an
admin-console field for a value with exactly one writer.

**Read the endpoints from each service's OIDC discovery document at request
time.** Both mocks serve one, and it is how a real client learns endpoints.
Rejected for the horizon problem: a discovery document advertises one set of
addresses, and the launch flow needs a browser-facing authorize URL and a
server-facing key set at the same time. A tool that took both from discovery
would send a real browser to a container name — and would pass every in-process
test, because in a test the two horizons are the same. It also puts a network
fetch in front of every login initiation.

**Required fields with no default.** The alternative the config module's own
rule points at, and the one this decision deliberately declines. It costs the
clean-checkout property above; it buys a startup refusal instead of a
first-request failure, which is a real advantage and the reason this is
contestable rather than obvious. If a deployment ever starts with one of these
wrong and nobody notices, this is the record to revisit.

**A single `OIDC_BASE_URL` the other three are derived from.** Fewer variables,
and wrong for the same reason discovery is: the browser-facing and server-facing
addresses of one provider are different hosts.

## Consequences

- Seven new lines in `.env.example` and seven new fields on `Settings`. The
  sync test derives both directions mechanically, so nothing was hand-listed.
- **`OIDC_ISSUER` looks like an address and is not one.** It is compared against
  the `iss` claim as a string (OIDC Core 1.0 §3.1.3.7) and is never fetched or
  redirected to, which is why it stays `mock-idp:8000` while the authorize URL
  beside it is `localhost:8081`. Anyone "fixing" it to match its neighbour breaks
  every web login.
- There is no `OIDC_CLIENT_SECRET`, and its absence is the design: the client is
  public and PKCE binds the code to it (RFC 7636). A secret appearing here later
  is a change of client type, not a configuration addition.
- The override file and `PUBLIC_BASE_URL` have to name the same address. Both
  mocks compare the tool's `redirect_uri` exactly, so a drift between them is a
  refusal that reads as a broken mock. `tests/conftest.py`'s `door_contract`
  holds the paths in one place for the same reason.
- E1 supersedes the first two fields when service addresses become registration
  columns. The OIDC block outlives that: it is not per-platform.
